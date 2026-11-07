# SPDX-License-Identifier: MIT
"""Ephemeral private test CA and short-lived localhost server certificate.

Apple requires serverAuth EKU and limits server certificate validity:
https://support.apple.com/en-us/103769
OpenSSL comes from the pinned Nix test SDK; no system trust store is changed.
"""
from pathlib import Path
import subprocess
import tempfile


class FixtureTLS:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='docker-fixture-tls-')
        self.root = Path(self.temporary.name)
        self.ca = self.root / 'ca.crt'
        self.certificate = self.root / 'localhost.crt'
        self.key = self.root / 'localhost.key'
        def run(*args):
            return subprocess.run(['openssl', *map(str, args)], check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, timeout=60).stdout
        try:
            self.version = run('version').strip()
            run('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256',
                '-keyout', self.root / 'ca.key', '-out', self.ca, '-days', '2',
                '-subj', '/CN=docker-purifier fixture CA',
                '-addext', 'basicConstraints=critical,CA:TRUE,pathlen:0',
                '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
            run('req', '-new', '-newkey', 'rsa:2048', '-nodes',
                '-keyout', self.key, '-out', self.root / 'localhost.csr',
                '-subj', '/CN=localhost')
            extensions = self.root / 'leaf.ext'
            extensions.write_text('basicConstraints=critical,CA:FALSE\n'
                                  'keyUsage=critical,digitalSignature,keyEncipherment\n'
                                  'extendedKeyUsage=serverAuth\n'
                                  'subjectAltName=DNS:localhost,IP:127.0.0.1\n')
            run('x509', '-req', '-sha256', '-in', self.root / 'localhost.csr',
                '-CA', self.ca, '-CAkey', self.root / 'ca.key', '-set_serial', '2',
                '-out', self.certificate, '-days', '1', '-extfile', extensions)
        except BaseException:
            self.close()
            raise

    def close(self):
        self.temporary.cleanup()
