# SPDX-License-Identifier: MIT
"""Validate the native OCI result and every blob's digest without a daemon."""
import hashlib,json,sys,tarfile
from pathlib import Path
root=Path(sys.argv[1]);seen=set()
def blob(digest):
 path=root/'blobs'/digest.replace(':','/');payload=path.read_bytes()
 assert 'sha256:'+hashlib.sha256(payload).hexdigest()==digest
 seen.add(digest);return payload
index=json.loads((root/'index.json').read_text())
for descriptor in index['manifests']:
 manifest=json.loads(blob(descriptor['digest']));configuration=json.loads(blob(manifest['config']['digest']))
 assert configuration['os']=='linux'
 for layer in manifest['layers']:blob(layer['digest'])
assert seen
print('native OCI layout and blob digests are valid')
