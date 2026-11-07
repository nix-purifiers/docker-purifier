# SPDX-License-Identifier: MIT
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import unittest
from unittest.mock import patch
from docker_purifier import cli


class ImageIdentity(unittest.TestCase):
    tag = 'localhost/nix-purifier-base:locked'
    config = b'{"architecture":"amd64","os":"linux","rootfs":{"type":"layers","diff_ids":[]}}'

    def check_saved(self, config=None, tag=None, corrupt=False):
        expected = 'sha256:' + hashlib.sha256(self.config).hexdigest()
        def command(args, **kwargs):
            if 'inspect' in args:
                return subprocess.CompletedProcess(args, 0, stdout='sha256:manifest-identity\n')
            self.assertIn('save', args)
            path = Path(args[args.index('--output') + 1])
            if corrupt:
                path.write_bytes(b'not an archive')
            else:
                with tarfile.open(path, 'w') as archive:
                    for name, payload in [('manifest.json', json.dumps([{'Config': 'config.json', 'RepoTags': [tag or self.tag]}]).encode()),
                                          ('config.json', config if config is not None else self.config)]:
                        member = tarfile.TarInfo(name)
                        member.size = len(payload)
                        archive.addfile(member, io.BytesIO(payload))
            return subprocess.CompletedProcess(args, 0)
        with patch.object(cli, 'run_unchecked', side_effect=command):
            return cli.image_matches(['--context', 'test'], self.tag, expected)

    def test_containerd_manifest_id_still_checks_raw_config(self):
        self.assertTrue(self.check_saved())

    def test_changed_config_rejected(self):
        self.assertFalse(self.check_saved(config=self.config + b' '))

    def test_wrong_tag_rejected(self):
        self.assertFalse(self.check_saved(tag='localhost/other:tag'))

    def test_corrupt_save_rejected(self):
        self.assertFalse(self.check_saved(corrupt=True))

    def test_legacy_config_id_avoids_save(self):
        with patch.object(cli, 'run_unchecked', return_value=subprocess.CompletedProcess([], 0, stdout='sha256:config\n')) as command:
            self.assertTrue(cli.image_matches([], self.tag, 'sha256:config'))
            self.assertEqual(command.call_count, 1)

    def test_save_timeout_rejects_and_cleans_workspace(self):
        saved_path = None
        def command(args, **kwargs):
            nonlocal saved_path
            if 'inspect' in args:
                return subprocess.CompletedProcess(args, 0, stdout='sha256:manifest')
            self.assertEqual(kwargs['timeout'], 300)
            saved_path = Path(args[args.index('--output') + 1])
            saved_path.write_bytes(b'partial')
            raise subprocess.TimeoutExpired(args, 300)
        with patch.object(cli, 'run_unchecked', side_effect=command):
            self.assertFalse(cli.image_matches([], self.tag, 'sha256:config'))
        self.assertFalse(saved_path.parent.exists())

    def test_missing_image_is_not_verified(self):
        with patch.object(cli, 'run_unchecked', return_value=subprocess.CompletedProcess([], 1)):
            self.assertFalse(cli.image_matches([], self.tag, 'sha256:config'))


class ArchiveMemberSafety(unittest.TestCase):
    def identity(self, manifest, config_path='config.json', duplicate=False, link=False):
        from docker_purifier.archive import config_identity
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as archive:
            payload = json.dumps(manifest).encode()
            member = tarfile.TarInfo('manifest.json')
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
            config = tarfile.TarInfo(config_path)
            if link:
                config.type = tarfile.SYMTYPE
                config.linkname = '/etc/passwd'
                archive.addfile(config)
            else:
                config.size = 2
                archive.addfile(config, io.BytesIO(b'{}'))
                if duplicate:
                    archive.addfile(config, io.BytesIO(b'{}'))
        stream.seek(0)
        with tarfile.open(fileobj=stream) as archive:
            return config_identity(archive, 'expected:tag')

    def test_ambiguous_and_missing_tags(self):
        for tags in (None, [], ['expected:tag', 'expected:tag'], ['expected:tag', 'other:tag']):
            with self.subTest(tags=tags), self.assertRaises(ValueError):
                self.identity([{'Config': 'config.json', 'RepoTags': tags}])

    def test_ambiguous_manifest(self):
        with self.assertRaises(ValueError):
            self.identity([{'Config': 'config.json', 'RepoTags': ['expected:tag']}] * 2)

    def test_missing_config(self):
        with self.assertRaises(ValueError):
            self.identity([{'RepoTags': ['expected:tag']}])

    def test_missing_config_member(self):
        with self.assertRaises(ValueError):
            self.identity([{'Config': 'absent.json', 'RepoTags': ['expected:tag']}])

    def test_unsafe_config_paths(self):
        for name in ('../secret', '/etc/passwd', 'blobs/../secret', './config.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.identity([{'Config': name, 'RepoTags': ['expected:tag']}], config_path=name)

    def test_duplicate_config_member(self):
        with self.assertRaises(ValueError):
            self.identity([{'Config': 'config.json', 'RepoTags': ['expected:tag']}], duplicate=True)

    def test_symlink_config_member(self):
        with self.assertRaises(ValueError):
            self.identity([{'Config': 'config.json', 'RepoTags': ['expected:tag']}], link=True)
