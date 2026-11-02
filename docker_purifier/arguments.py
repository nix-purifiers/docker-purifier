# SPDX-License-Identifier: MIT
"""Locate native build context without rewriting ordinary Docker options."""
from pathlib import Path
GLOBAL_VALUES={'--config','--context','-c','--host','-H','--log-level','-l','--tlscacert','--tlscert','--tlskey'}
VALUES={'--add-host','--annotation','--attest','--build-arg','--builder','--cache-from','--cache-to','--call','--cgroup-parent','--file','-f','--iidfile','--label','--metadata-file','--network','--no-cache-filter','--output','-o','--platform','--secret','--shm-size','--ssh','--tag','-t','--target','--ulimit','--build-context','--allow','--progress','--policy'}
BOOLS={'--check','--debug','-D','--disable-content-trust','--load','--no-cache','--pull','--push','--quiet','-q','--rm','--force-rm','--squash','--help','-h'}
PROTECTED={'--pull','--build-context'}
def command(args):
 i=0
 while i<len(args) and args[i].startswith('-'):
  key=args[i].split('=',1)[0]
  if key in GLOBAL_VALUES and '=' not in args[i]:i+=1
  i+=1
 return args[:i],args[i:]
def build(args):
 prefix,rest=command(args);plugin_builder=None
 if rest[:1]==['build']:body=rest[1:];prefix+=['build']
 elif rest[:1]==['buildx']:
  plugin=rest[1:];i=0
  while i<len(plugin) and plugin[i].startswith('-'):
   key=plugin[i].split('=',1)[0]
   if key=='--builder':
    if '=' in plugin[i]:plugin_builder=plugin[i].split('=',1)[1]
    else:i+=1;plugin_builder=plugin[i] if i<len(plugin) else None
   i+=1
  if plugin[i:i+1]!=['build']:return None
  prefix+=['buildx',*plugin[:i],'build'];body=plugin[i+1:]
 else:return None
 values={};positionals=[];forbidden=[];i=0
 while i<len(body):
  arg=body[i];key,equal,value=arg.partition('=')
  if arg=='--':positionals.extend(body[i+1:]);break
  if key=='--platform' and key in values:raise ValueError('locked builds support one native platform')
  if key in VALUES:
   if not equal:
    i+=1
    if i==len(body):raise ValueError('missing native option value: '+key)
    value=body[i]
   values[key]=value
  elif key in BOOLS:value=value if equal else 'true'
  elif key in ('--provenance','--sbom'):
   if not equal and i+1<len(body) and (body[i+1] in ('true','false') or '=' in body[i+1]):i+=1;value=body[i]
  elif arg.startswith(('-f','-t','-o')) and len(arg)>2:key=arg[:2];value=arg[2:];values[key]=value
  elif arg.startswith('-') and arg!='-':raise ValueError('unsupported native build option: '+arg)
  else:positionals.append(arg)
  if key=='-f':values['--file']=value
  if key in PROTECTED:
   if not ((key=='--network' and value=='none') or (key=='--pull' and value=='false')):forbidden.append(key)
  i+=1
 if len(positionals)!=1:raise ValueError('locked builds require exactly one local build context')
 context=positionals[0]
 if context=='-' or '://' in context or context.startswith('git@'):raise ValueError('locked builds require a checked-out local build context')
 root=Path(context).resolve()
 dockerfile=Path(values.get('--file',values.get('-f',''))).resolve() if '--file' in values or '-f' in values else root/'Dockerfile'
 return {'prefix':prefix,'body':body,'root':root,'dockerfile':dockerfile,'platform':values.get('--platform'),'forbidden':forbidden,'builder':values.get('--builder',plugin_builder),'dockerCommand':rest[:1]==['build']}
