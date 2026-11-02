# SPDX-License-Identifier: MIT
"""OCI native digests and Dockerfile input validation."""
import hashlib,json,re
from pathlib import Path
FIX='; run docker-purifier lock'
PLATFORMS={'linux/amd64':'x86_64-linux','linux/arm64':'aarch64-linux'}
def seal(data):
 data={k:v for k,v in data.items() if k!='contentHash'}
 return {**data,'contentHash':hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()}
def digest(data):return 'sha256:'+hashlib.sha256(data).hexdigest()
def target_name(root,dockerfile):
 try:return str(dockerfile.relative_to(root))
 except ValueError:return dockerfile.name
def inputs(root,dockerfile):
 name=target_name(root,dockerfile);files={name:dockerfile}
 if (root/'.dockerignore').exists():files['.dockerignore']=root/'.dockerignore'
 ignore=dockerfile.with_name(dockerfile.name+'.dockerignore')
 if ignore.exists():files[name+'.dockerignore']=ignore
 return {key:hashlib.sha256(path.read_bytes()).hexdigest() for key,path in files.items()}

def instructions(text):
 if re.search(r'^\s*#\s*(?:syntax|escape)\s*=',text,re.M|re.I):raise ValueError('external Dockerfile frontends and alternate escape characters are not supported yet'+FIX)
 for line in text.replace('\\\n',' ').splitlines():
  line=line.strip()
  if line and not line.startswith('#'):
   parts=line.split(None,1);instruction=parts[0];value=parts[1] if len(parts)>1 else ''
   yield instruction.upper(),value.strip()
def references(text):
 stages=[];refs=[]
 for command,value in instructions(text):
  if command=='FROM':
   words=value.split()
   if not words or words[0].startswith('--') or '$' in value:raise ValueError('FROM requires a literal native-platform image reference'+FIX)
   image=words[0]
   if image.lower()!='scratch' and image.lower() not in stages:refs.append(image)
   if len(words)>1:
    if len(words)!=3 or words[1].lower()!='as':raise ValueError('invalid FROM instruction'+FIX)
    stages.append(words[2].lower())
   else:stages.append(str(len(stages)))
  elif command in ('COPY','ADD'):
   source=re.search(r'(?:^|\s)--from=([^\s]+)',value)
   if source:
    name=source[1]
    if name.isdigit():
     if int(name)>=len(stages):raise ValueError('COPY references a missing stage'+FIX)
    elif name.lower() not in stages:
     if '$' in name:raise ValueError('COPY --from requires a literal reference'+FIX)
     refs.append(name)
   if command=='ADD' and re.search(r'(?:https?|git|ssh)://|git@',value):raise ValueError('remote ADD inputs must be vendored before locking'+FIX)
  elif command=='RUN' and any(token in value for token in ('--mount=', '<<')):raise ValueError('RUN mounts are not supported yet'+FIX)
 if set(ref.lower() for ref in refs)&set(stages):raise ValueError('stage aliases must differ from external image references'+FIX)
 if not stages:raise ValueError('Dockerfile needs a FROM instruction'+FIX)
 return sorted(set(refs))
def repository(reference):
 if not re.fullmatch(r'[a-zA-Z0-9_.:/@-]+',reference) or '..' in reference or '://' in reference:raise ValueError('unsupported image reference'+FIX)
 name=reference.split('@',1)[0]
 if ':' in name.rsplit('/',1)[-1]:name=name.rsplit(':',1)[0]
 first=name.split('/')[0]
 if '/' not in name or not ('.' in first or ':' in first or first=='localhost'):name='docker.io/'+name
 registry,path=name.split('/',1)
 if registry in ('docker.io','index.docker.io','registry-1.docker.io'):
  registry='registry-1.docker.io';path=path if '/' in path else 'library/'+path;name='docker.io/'+path
 if not path or any(part in ('','..','.') for part in path.split('/')):raise ValueError('invalid repository path'+FIX)
 return name,registry,path
def alias(ref):return hashlib.sha256(ref.encode()).hexdigest()[:20]
def problems(root,path,data):
 try:
  if not isinstance(data,dict) or data.get('version')!=1:return ['unsupported lock format'+FIX]
  if data.get('contentHash')!=seal(data)['contentHash']:return ['contentHash mismatch'+FIX]
  if data.get('inputs')!=inputs(root,path):return ['Dockerfile or ignore rules changed'+FIX]
  refs=references(path.read_text())
  if sorted(data.get('images',{}))!=refs:return ['missing image entry'+FIX]
  if not isinstance(data.get('platforms'),list) or not data['platforms'] or len(set(data['platforms']))!=len(data['platforms']) or any(p not in PLATFORMS for p in data['platforms']):return ['invalid platform selection'+FIX]
  for ref,image in data['images'].items():
   errors=image_problems(ref,image,data['platforms'])
   if errors:return errors
  return []
 except (ValueError,KeyError,TypeError,OSError) as error:return [str(error)+FIX]

def image_problems(ref,image,platforms):
 try:
  repository(ref)
  if not isinstance(image,dict) or not re.fullmatch('sha256:[0-9a-f]{64}',image.get('sourceDigest','')):return ['invalid image digest'+FIX]
  if not isinstance(image.get('platforms'),dict) or set(image['platforms'])!=set(platforms):return ['missing image platform'+FIX]
  for platform,spec in image['platforms'].items():
   if platform not in PLATFORMS:return ['unsupported platform'+FIX]
   payload=spec['manifest'].encode();manifest=json.loads(payload)
   if digest(payload)!=spec['digest'] or manifest.get('schemaVersion')!=2:return ['manifest digest mismatch'+FIX]
   config=json.loads(spec['config'])
   if digest(spec['config'].encode())!=manifest['config']['digest']:return ['image config digest mismatch'+FIX]
   if (config.get('config') or {}).get('OnBuild'):return ['ONBUILD base image triggers are not supported yet'+FIX]
   if config.get('os')!='linux' or config.get('architecture')!=platform.split('/')[1]:return ['base image has a different platform'+FIX]
   for entry in [manifest['config'],*manifest['layers']]:
    if not re.fullmatch('sha256:[0-9a-f]{64}',entry['digest']) or not isinstance(entry.get('size'),int) or entry['size']<0:return ['unsupported OCI digest or size'+FIX]
    if entry.get('urls'):return ['foreign image layers are not supported yet'+FIX]
  return []
 except (ValueError,KeyError,TypeError,AttributeError):return ['invalid OCI metadata'+FIX]
