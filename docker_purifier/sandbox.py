# SPDX-License-Identifier: MIT
"""Import locked OCI inputs and invoke native Buildah with named contexts."""
import json,os,subprocess,sys
from pathlib import Path
from . import lock
sidecar,layouts,platform,dockerfile,build_args=sys.argv[1:]
data=json.loads(Path(sidecar).read_text())
base=['buildah','--root','/tmp/container-storage','--runroot','/tmp/container-run','--storage-driver=vfs']
contexts=[]
for ref,image in data['images'].items():
 layout=Path(layouts)/lock.alias(ref)/lock.PLATFORMS[platform]
 tag='localhost/purifier-base-'+lock.alias(ref)+':locked'
 subprocess.run([*base,'pull','--signature-policy','/tmp/policy.json','oci:'+str(layout)+':purifier'],check=True)
 image_id=json.loads(image['platforms'][platform]['manifest'])['config']['digest'].split(':',1)[1]
 subprocess.run([*base,'tag',image_id,tag],check=True)
 contexts.extend(['--build-context',ref+'=container-image://'+tag])
arguments=[]
for key,value in sorted(json.loads(build_args).items()):arguments.extend(['--build-arg',key+'='+str(value)])
os.environ.pop('SOURCE_DATE_EPOCH',None)
subprocess.run([*base,'build','--signature-policy','/tmp/policy.json','--pull=never','--isolation=chroot','--network=host','--security-opt=label=disable','--timestamp=1','--format=oci',*contexts,*arguments,'-f',dockerfile,'-t','purifier-result','.'],check=True)
