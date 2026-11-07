# SPDX-License-Identifier: MIT
import socket
import ssl
import subprocess
import unittest
import urllib.error
import urllib.request
from registry import Registry


class RegistryTLS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = Registry().start()

    @classmethod
    def tearDownClass(cls):
        cls.registry.stop()

    def opener(self, context):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                          urllib.request.HTTPSHandler(context=context))

    def test_trusted_chain_and_hostname(self):
        context = ssl.create_default_context(cafile=str(self.registry.tls.ca))
        with self.opener(context).open('https://' + self.registry.host + '/v2/', timeout=10) as response:
            self.assertEqual(response.read(), b'{}')

    def test_untrusted_ca_is_rejected(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with self.assertRaises(urllib.error.URLError) as failure:
            self.opener(context).open('https://' + self.registry.host + '/v2/', timeout=10)
        self.assertIsInstance(failure.exception.reason, ssl.SSLCertVerificationError)

    def test_wrong_hostname_is_rejected(self):
        context = ssl.create_default_context(cafile=str(self.registry.tls.ca))
        with socket.create_connection(self.registry.server.server_address, timeout=10) as connection:
            with self.assertRaises(ssl.SSLCertVerificationError):
                context.wrap_socket(connection, server_hostname='wrong.invalid')

    def test_leaf_profile_and_lifetime(self):
        certificate = self.registry.tls.certificate
        decoded = ssl._ssl._test_decode_cert(str(certificate))
        lifetime = ssl.cert_time_to_seconds(decoded['notAfter']) - ssl.cert_time_to_seconds(decoded['notBefore'])
        self.assertEqual(lifetime, 86400)
        self.assertIn(('DNS', 'localhost'), decoded['subjectAltName'])
        self.assertIn(('IP Address', '127.0.0.1'), decoded['subjectAltName'])
        profile = subprocess.check_output(['openssl', 'x509', '-in', str(certificate), '-noout', '-text'], text=True)
        for expected in ('CA:FALSE', 'TLS Web Server Authentication', '2048 bit', 'sha256WithRSAEncryption'):
            self.assertIn(expected, profile)
        subprocess.run(['openssl', 'verify', '-purpose', 'sslserver', '-verify_hostname', 'localhost',
                        '-CAfile', str(self.registry.tls.ca), str(certificate)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
