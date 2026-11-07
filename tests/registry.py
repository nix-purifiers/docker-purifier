# SPDX-License-Identifier: MIT
"""A real TLS OCI registry serving two versions of tiny empty Linux images."""
import hashlib,http.server,json,ssl,threading
from tls_fixture import FixtureTLS
INDEX='application/vnd.oci.image.index.v1+json';MANIFEST='application/vnd.oci.image.manifest.v1+json';CONFIG='application/vnd.oci.image.config.v1+json'
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def digest(payload):return 'sha256:'+hashlib.sha256(payload).hexdigest()
class Registry:
 def __init__(self):
  self.objects={};self.tags={'first':1,'second':1};self.indexes={}
  for version in (1,2):
   manifests=[]
   for architecture in ('amd64','arm64'):
    configuration=encode({'architecture':architecture,'os':'linux','created':'1970-01-01T00:00:01Z','config':{'Env':['FIXTURE_VERSION='+str(version)]},'rootfs':{'type':'layers','diff_ids':[]}})
    config=self.put(configuration,CONFIG)
    manifest=self.put(encode({'schemaVersion':2,'mediaType':MANIFEST,'config':config,'layers':[]}),MANIFEST)
    manifests.append({**manifest,'platform':{'os':'linux','architecture':architecture}})
   self.indexes[version]=self.put(encode({'schemaVersion':2,'mediaType':INDEX,'manifests':manifests}),INDEX)
  fixture=self
  class Handler(http.server.BaseHTTPRequestHandler):
   def do_GET(self):
    if self.path=='/v2/':payload=b'{}';kind='application/json'
    else:
     parts=self.path.split('/')
     if len(parts)!=5 or parts[1]!='v2' or parts[2] not in fixture.tags or parts[3] not in ('manifests','blobs'):self.send_error(404);return
     key=fixture.indexes[fixture.tags[parts[2]]]['digest'] if parts[4]=='latest' else parts[4]
     if key not in fixture.objects:self.send_error(404);return
     payload,kind=fixture.objects[key]
    self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(payload)));self.send_header('Docker-Distribution-Api-Version','registry/2.0');self.send_header('Docker-Content-Digest',digest(payload));self.end_headers();self.wfile.write(payload)
   def log_message(self,*args):pass
  self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
  self.tls=FixtureTLS()
  context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(self.tls.certificate,self.tls.key);self.server.socket=context.wrap_socket(self.server.socket,server_side=True)
  self.host='localhost:'+str(self.server.server_port)
 def put(self,payload,kind):
  key=digest(payload);self.objects[key]=(payload,kind)
  return {'digest':key,'size':len(payload),'mediaType':kind}
 def start(self):threading.Thread(target=self.server.serve_forever,daemon=True).start();return self
 def stop(self):
  self.server.shutdown();self.server.server_close();self.tls.close()
