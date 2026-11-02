# SPDX-License-Identifier: MIT
import unittest
from docker_purifier import lock
class Dockerfiles(unittest.TestCase):
 def test_stages(self):
  self.assertEqual(lock.references('FROM alpine:3 AS base\nFROM base\nCOPY --from=busybox:1 /bin/sh /bin/sh\n'),['alpine:3','busybox:1'])
 def test_continuation(self):
  self.assertEqual(lock.references('FROM \\\n alpine:3\n'),['alpine:3'])
 def test_reject_unlocked_sources(self):
  for text in ['FROM ${BASE}\n','# syntax=docker/dockerfile:1\nFROM scratch\n','FROM scratch\nADD https://x/a /a\n','FROM --platform=linux/amd64 alpine\n']:
   with self.assertRaises(ValueError):lock.references(text)
 def test_repository(self):
  self.assertEqual(lock.repository('alpine:3'),('docker.io/library/alpine','registry-1.docker.io','library/alpine'))
  self.assertEqual(lock.repository('quay.io/prometheus/busybox:latest'),('quay.io/prometheus/busybox','quay.io','prometheus/busybox'))
if __name__=='__main__':unittest.main()
