# SPDX-License-Identifier: MIT
import argparse,json,os,subprocess,sys,tempfile
from pathlib import Path
from . import lock
SKOPEO=os.environ.get('DOCKER_PURIFIER_SKOPEO','skopeo')
DOCKER=os.environ.get('DOCKER_PURIFIER_DOCKER','docker')
def run(args,**kwargs):return subprocess.run(list(map(str,args)),check=True,**kwargs)
def run_unchecked(args,**kwargs):return subprocess.run(list(map(str,args)),check=False,**kwargs)
def raw(reference,config=False):
 return run([SKOPEO,'inspect','--config' if config else '--raw','docker://'+reference],stdout=subprocess.PIPE).stdout
def write(path,text):
 path.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',dir=path.parent,delete=False) as output:output.write(text);temporary=Path(output.name)
 temporary.replace(path)
def load(path):return json.loads(path.read_text())
def checked(root,dockerfile,sidecar):
 try:data=load(sidecar);errors=lock.problems(root,dockerfile,data)
 except (ValueError,OSError) as error:raise ValueError(str(error)+lock.FIX) from error
 if errors:raise ValueError('\n'.join(errors))
 return data
def resolve(ref,platforms,pin=None):
 repository,registry,path=lock.repository(ref)
 source=raw(repository+'@'+pin if pin else ref);index=json.loads(source);source_digest=lock.digest(source)
 result={'sourceDigest':source_digest,'platforms':{}}
 for platform in platforms:
  os_name,architecture=platform.split('/')
  if 'manifests' in index:
   matches=[m for m in index['manifests'] if m.get('platform',{}).get('os')==os_name and m.get('platform',{}).get('architecture')==architecture and m.get('platform',{}).get('variant','') in ('','v8')]
   if len(matches)!=1:raise ValueError(f'{ref} does not have a unique {platform} manifest'+lock.FIX)
   manifest_raw=raw(repository+'@'+matches[0]['digest'])
   if lock.digest(manifest_raw)!=matches[0]['digest']:raise ValueError('registry manifest digest mismatch')
  else:manifest_raw=source
  manifest=json.loads(manifest_raw)
  # Native skopeo --config renders JSON, while the config digest covers the
  # original blob bytes. Fetch those bytes through the same OCI transport.
  from .oci import request
  url=f'https://{registry}/v2/{path}/blobs/{manifest["config"]["digest"]}'
  with request(url) as response:configuration=response.read()
  if lock.digest(configuration)!=manifest['config']['digest']:raise ValueError('registry config digest mismatch')
  result['platforms'][platform]={'digest':lock.digest(manifest_raw),'manifest':manifest_raw.decode(),'config':configuration.decode()}
 return result
def do_lock(root,dockerfile,sidecar,update=False,platforms=('linux/amd64','linux/arm64'),names=()):
 refs=lock.references(dockerfile.read_text());previous=None
 if sidecar.exists():
  try:
   candidate=load(sidecar)
   if candidate.get('version')==1 and candidate.get('contentHash')==lock.seal(candidate)['contentHash']:previous=candidate
  except ValueError:pass
 if set(names)-set(refs):raise ValueError('update names must be literal Dockerfile image references')
 images={}
 for ref in refs:
  old=previous.get('images',{}).get(ref) if previous and isinstance(previous.get('images'),dict) else None
  if old and not (update and (not names or ref in names)):
   if not lock.image_problems(ref,old,platforms):images[ref]=old
   elif isinstance(old,dict) and isinstance(old.get('sourceDigest'),str):images[ref]=resolve(ref,platforms,pin=old['sourceDigest'])
   else:images[ref]=resolve(ref,platforms)
  else:images[ref]=resolve(ref,platforms)
 ignore=dockerfile.with_name(dockerfile.name+'.dockerignore')
 if not ignore.exists():ignore=root/'.dockerignore'
 marker='# docker-purifier generated cache\n.docker-purifier\n'
 text=ignore.read_text() if ignore.exists() else ''
 text=text.replace(marker,'')
 write(ignore,text+('' if not text or text.endswith('\n') else '\n')+marker)
 data=lock.seal({'version':1,'inputs':lock.inputs(root,dockerfile),'dockerfile':lock.target_name(root,dockerfile),'platforms':list(platforms),'images':images})
 errors=lock.problems(root,dockerfile,data)
 if errors:raise ValueError('\n'.join(errors))
 write(sidecar,json.dumps(data,indent=2,sort_keys=True)+'\n')
 print(f'Locked {len(images)} image references in {sidecar}')
def realize(root,dockerfile,sidecar,target):
 args=['nix','build','--impure','--file',os.environ['DOCKER_PURIFIER_REALIZE'],'--argstr','project',root,'--argstr','dockerfile',dockerfile,'--argstr','lockFile',sidecar,'--argstr','target',target,'--no-link','--print-out-paths']
 return Path(run(args,text=True,stdout=subprocess.PIPE).stdout.strip())
def prefetch(root,dockerfile,sidecar):
 data=checked(root,dockerfile,sidecar)
 cache=sidecar.parent/'.docker-purifier'/lock.alias(str(sidecar));cache.mkdir(parents=True,exist_ok=True)
 for target in ('dependencies','archives','runtime'):
  result=realize(root,dockerfile,sidecar,target)
  run(['nix-store','--add-root',cache/target,'--indirect','--realise',result],stdout=subprocess.DEVNULL)
 return data,cache/'dependencies'
def native(args,root,dockerfile,sidecar,explicit_lock=False,explicit_dockerfile=False):
 from . import arguments
 if '--help' in args or '-h' in args:
  if not sidecar.exists():print('docker-purifier: no lockfile; using ordinary impure Docker',file=sys.stderr)
  os.execv(DOCKER,[DOCKER,*args])
 try:parsed=arguments.build(args)
 except ValueError:
  candidates=[sidecar] if explicit_lock else [sidecar,*[Path(arg).resolve()/'docker-purifier.lock.json' for arg in args if not arg.startswith('-')]]
  if any(path.is_file() for path in candidates):raise
  parsed=None
 if parsed:
  root=parsed['root']
  if not explicit_lock:sidecar=root/'docker-purifier.lock.json'
  if not explicit_dockerfile:dockerfile=parsed['dockerfile']
 if not sidecar.exists():
  print('docker-purifier: no lockfile; using ordinary impure Docker',file=sys.stderr);os.execv(DOCKER,[DOCKER,*args])
 if not parsed:
  _,commands=arguments.command(args)
  if commands[:1]==['compose'] or (commands[:1]==['buildx'] and 'bake' in commands):raise ValueError('locked Compose/Bake builds are not supported; use docker build')
  os.execv(DOCKER,[DOCKER,*args])
 if parsed['forbidden']:raise ValueError('locked builds supply their own image contexts and pull policy: '+', '.join(parsed['forbidden']))
 data=checked(root,dockerfile,sidecar)
 platform=parsed['platform'] or os.environ.get('DOCKER_DEFAULT_PLATFORM') or ('linux/arm64' if os.uname().machine in ('aarch64','arm64') else 'linux/amd64')
 if platform not in data['platforms']:raise ValueError('platform is absent from the lock'+lock.FIX)
 native_platform='linux/arm64' if os.uname().machine in ('aarch64','arm64') else 'linux/amd64'
 if platform!=native_platform:raise ValueError('cross-platform host builds are not supported yet')
 _,dependencies=prefetch(root,dockerfile,sidecar)
 global_args,_=arguments.command(args)
 selected=parsed['builder'] or os.environ.get('BUILDX_BUILDER')
 if not selected and parsed['dockerCommand']:
  selected=run([DOCKER,*global_args,'context','show'],stdout=subprocess.PIPE,text=True).stdout.strip()
 driver=run([DOCKER,*global_args,'buildx','inspect',*([selected] if selected else []),'--format','{{.Driver}}'],stdout=subprocess.PIPE,text=True).stdout.strip()
 extra=['--pull=false']
 for ref,image in data['images'].items():
  layout=dependencies/lock.alias(ref)/lock.PLATFORMS[platform]
  if driver=='docker':
   archives=dependencies.parent/'archives'
   metadata=load(archives/(lock.alias(ref)+'.json'));tag=metadata['tag']
   inspect=run_unchecked([DOCKER,*global_args,'image','inspect',tag,'--format','{{.Id}}'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
   if inspect.returncode or inspect.stdout.strip()!=metadata['imageId']:
    run([DOCKER,*global_args,'load','--input',archives/(lock.alias(ref)+'.tar')],stdout=sys.stderr)
    identity=run([DOCKER,*global_args,'image','inspect',tag,'--format','{{.Id}}'],stdout=subprocess.PIPE,text=True).stdout.strip()
    if identity!=metadata['imageId']:raise ValueError('Docker did not load the Nix-resolved image identity')
   context='docker-image://'+tag
  else:context='oci-layout://'+str(layout)+'@'+image['platforms'][platform]['digest']
  extra.extend(['--build-context',ref+'='+context])
 os.execv(DOCKER,[DOCKER,*parsed['prefix'],*extra,*parsed['body']])

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--project',default='.');parser.add_argument('--dockerfile');parser.add_argument('--lockfile',default=os.environ.get('DOCKER_PURIFIER_LOCKFILE'))
 sub=parser.add_subparsers(dest='command',required=True)
 for name in ('lock','update'):
  p=sub.add_parser(name);p.add_argument('--platform',action='append');
  if name=='update':p.add_argument('names',nargs='*')
 sub.add_parser('prefetch');p=sub.add_parser('native');p.add_argument('args',nargs=argparse.REMAINDER)
 p=sub.add_parser('publish');p.add_argument('--repo',required=True);p.add_argument('--tag',required=True)
 a=parser.parse_args();root=Path(a.project).resolve();dockerfile=Path(a.dockerfile).resolve() if a.dockerfile else root/'Dockerfile'
 sidecar=Path(a.lockfile).resolve() if a.lockfile else root/'docker-purifier.lock.json'
 try:
  if a.command in ('lock','update'):do_lock(root,dockerfile,sidecar,a.command=='update',a.platform or tuple(lock.PLATFORMS),getattr(a,'names',()))
  elif a.command=='prefetch':prefetch(root,dockerfile,sidecar)
  elif a.command=='native':native(a.args[1:] if a.args[:1]==['--'] else a.args,root,dockerfile,sidecar,bool(a.lockfile),bool(a.dockerfile))
  else:
   checked(root,dockerfile,sidecar);release=realize(root,dockerfile,sidecar,'release')
   run(['gh','release','create',a.tag,*sorted(release.iterdir()),'--repo',a.repo,'--title',a.tag,'--generate-notes'])
 except (ValueError,OSError,subprocess.CalledProcessError) as error:parser.exit(1,f'docker-purifier: {error}{lock.FIX}\n')
if __name__=='__main__':main()
