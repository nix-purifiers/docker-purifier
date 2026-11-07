# SPDX-License-Identifier: MIT
"""Normalize native archives and verify their raw configuration identity."""
import hashlib,json,sys,tarfile
from pathlib import Path,PurePosixPath

def regular_member(archive,name):
 if not isinstance(name,str) or not name or '\\' in name:raise ValueError('invalid Docker archive member path')
 path=PurePosixPath(name)
 if path.is_absolute() or '..' in path.parts or str(path)!=name:raise ValueError('unsafe Docker archive member path')
 matches=[member for member in archive.getmembers() if member.name==name]
 if len(matches)!=1 or not matches[0].isfile():raise ValueError('missing, ambiguous or non-regular Docker archive member')
 return archive.extractfile(matches[0])

def config_identity(archive,tag):
 with regular_member(archive,'manifest.json') as payload:manifest=json.load(payload)
 if not isinstance(manifest,list) or len(manifest)!=1 or not isinstance(manifest[0],dict) or manifest[0].get('RepoTags')!=[tag]:raise ValueError('native Docker archive has unexpected image tags')
 digest=hashlib.sha256()
 with regular_member(archive,manifest[0].get('Config')) as configuration:
  for block in iter(lambda:configuration.read(1024*1024),b''):digest.update(block)
 return 'sha256:'+digest.hexdigest()

def main():
 source,destination,metadata,tag=sys.argv[1:]
 with tarfile.open(source) as original,tarfile.open(destination,'w',format=tarfile.PAX_FORMAT) as result:
  identity=config_identity(original,tag)
  for member in sorted(original.getmembers(),key=lambda entry:entry.name):
   member.uid=member.gid=0;member.uname=member.gname='';member.mtime=1;member.pax_headers={}
   member.mode=0o755 if member.isdir() else 0o644
   result.addfile(member,original.extractfile(member) if member.isfile() else None)
 Path(metadata).write_text(json.dumps({'tag':tag,'imageId':identity},sort_keys=True)+'\n')

if __name__=='__main__':main()
