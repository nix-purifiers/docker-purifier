# SPDX-License-Identifier: MIT
"""Normalize a native Docker archive and record its actual config identity."""
import hashlib,json,sys,tarfile
from pathlib import Path
source,destination,metadata,tag=sys.argv[1:]
with tarfile.open(source) as original,tarfile.open(destination,'w',format=tarfile.PAX_FORMAT) as result:
 manifest=json.load(original.extractfile('manifest.json'))
 if len(manifest)!=1 or manifest[0]['RepoTags']!=[tag]:raise ValueError('native Docker archive has unexpected image tags')
 configuration=original.extractfile(manifest[0]['Config']).read()
 identity='sha256:'+hashlib.sha256(configuration).hexdigest()
 for member in sorted(original.getmembers(),key=lambda entry:entry.name):
  member.uid=member.gid=0;member.uname=member.gname='';member.mtime=1;member.pax_headers={}
  member.mode=0o755 if member.isdir() else 0o644
  result.addfile(member,original.extractfile(member) if member.isfile() else None)
Path(metadata).write_text(json.dumps({'tag':tag,'imageId':identity},sort_keys=True)+'\n')
