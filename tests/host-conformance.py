# SPDX-License-Identifier: MIT
"""Native registry resolution, external release and ordinary Docker workflow."""
import functools,http.server,json,os,shutil,ssl,subprocess,sys,tempfile,threading,time
from pathlib import Path
from registry import Registry
SOURCE=Path(__file__).resolve().parents[1]
def run(args,**kwargs):return subprocess.run(list(map(str,args)),check=True,text=True,**kwargs)
def verify_image(directory,expected):
 index=json.loads((directory/'index.json').read_text());blob=lambda digest:directory/'blobs'/digest.replace(':','/')
 manifest=json.loads(blob(index['manifests'][0]['digest']).read_text());config=json.loads(blob(manifest['config']['digest']).read_text())
 assert 'FIXTURE_VERSION='+str(expected) in config['config']['Env'],config
case=sys.argv[1]
with tempfile.TemporaryDirectory(prefix='docker-conformance-') as temporary:
 temp=Path(temporary);run(['nix','build',SOURCE,'--out-link',temp/'cli'])
 cli=temp/'cli/bin/docker-purifier';docker=temp/'cli/bin/docker'
 root=temp/'project';root.mkdir();sidecar=temp/'locks/docker.json' if case=='external' else root/'docker-purifier.lock.json'
 bundle=temp/'registry-ca.pem'
 roots=''.join(ssl.DER_cert_to_PEM_cert(cert) for cert in ssl.create_default_context().get_ca_certs(binary_form=True))
 bundle.write_text(roots)
 env={**os.environ,'SSL_CERT_FILE':str(bundle),'NIX_SSL_CERT_FILE':str(bundle)}
 def purifier(command,*args):return run([cli,'--project',root,'--lockfile',sidecar,command,*args],env=env)
 if case in ('relock','update'):
  registry=Registry().start()
  bundle.write_text(roots+registry.tls.ca.read_text())
  first=registry.host+'/first:latest';second=registry.host+'/second:latest'
  (root/'Dockerfile').write_text(f'FROM {first} AS builder\nCOPY version.txt /version.txt\nFROM {second}\nCOPY --from=builder /version.txt /version.txt\n')
  (root/'version.txt').write_text('local source\n')
  try:
   purifier('lock');original=sidecar.read_bytes();initial=json.loads(original)
   purifier('lock');assert sidecar.read_bytes()==original
   sidecar.write_text('{broken');purifier('lock');assert sidecar.read_bytes()==original
   registry.tags={'first':2,'second':2}
   if case=='relock':
    (root/'Dockerfile').write_text((root/'Dockerfile').read_text()+'\n')
    purifier('lock');assert json.loads(sidecar.read_text())['images']==initial['images']
    expected=1
   else:
    purifier('update',first);partial=json.loads(sidecar.read_text())
    assert partial['images'][first]['sourceDigest']!=initial['images'][first]['sourceDigest']
    assert partial['images'][second]==initial['images'][second]
    purifier('update');assert json.loads(sidecar.read_text())['images'][second]['sourceDigest']!=initial['images'][second]['sourceDigest']
    expected=2
   purifier('prefetch')
  finally:registry.stop()
  # The local registry is gone before the real packaged Nix builder runs.
  run(['nix','build','--impure','--file',temp/'cli/lib/docker-purifier/nix/realize.nix','--argstr','project',root,'--argstr','dockerfile',root/'Dockerfile','--argstr','lockFile',sidecar,'--argstr','target','release','--out-link',temp/'release'])
  import tarfile
  unpack=temp/'image';unpack.mkdir()
  with tarfile.open(temp/'release/image.oci.tar.gz') as archive:archive.extractall(unpack,filter='data')
  verify_image(unpack,expected)
 elif case in ('external','native'):
  shutil.copytree(SOURCE/'examples/hello',root,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.docker-purifier','docker-purifier.lock.json'))
  sidecar.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/'examples/hello/docker-purifier.lock.json',sidecar)
  original=sidecar.read_bytes();purifier('lock');assert sidecar.read_bytes()==original;purifier('prefetch')
  if case=='external':
   assert not (root/'docker-purifier.lock.json').exists()
   run(['nix','build','--impure','--file',temp/'cli/lib/docker-purifier/nix/realize.nix','--argstr','project',root,'--argstr','dockerfile',root/'Dockerfile','--argstr','lockFile',sidecar,'--argstr','target','release','--no-link'])
  else:
   run([docker,'info'],cwd=root)
   tag='purifier-conformance:'+str(os.getpid())
   try:
    run([docker,'build','.','--load','-t',tag],cwd=root)
    output=run([docker,'run','--rm','--network=none',tag],cwd=root,capture_output=True).stdout
    assert output=='hello from locked Docker dependencies\n',output
    served=temp/'served';served.mkdir();(served/'network.txt').write_text('host build network is available\n')
    server=http.server.ThreadingHTTPServer(('0.0.0.0',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=served))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
     with (root/'Dockerfile').open('a') as file:file.write('ARG PURIFIER_TEST_URL\nRUN wget -qO /network.txt "$PURIFIER_TEST_URL"\n')
     purifier('lock');original=sidecar.read_bytes()
     run([docker,'build','.','--load','-t',tag,'--add-host','host.docker.internal:host-gateway','--build-arg','PURIFIER_TEST_URL=http://host.docker.internal:'+str(server.server_port)+'/network.txt'],cwd=root)
     output=run([docker,'run','--rm','--network=none','--entrypoint','cat',tag,'/network.txt'],cwd=root,capture_output=True).stdout
     assert output=='host build network is available\n',output
    finally:server.shutdown();server.server_close()
   finally:subprocess.run([str(docker),'image','rm','-f',tag],cwd=root)
   assert sidecar.read_bytes()==original
 else:raise ValueError(case)
 sidecar.unlink()
 fallback=run([docker,'--version'],cwd=root,capture_output=True,env={**os.environ,'DOCKER_PURIFIER_LOCKFILE':str(sidecar)})
 assert 'ordinary impure Docker' in fallback.stderr
print(case+': native OCI resolution and offline checks passed')
