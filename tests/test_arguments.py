# SPDX-License-Identifier: MIT
import unittest
from pathlib import Path
from docker_purifier.arguments import build
class Arguments(unittest.TestCase):
 def test_context_before_tag(self):
  self.assertEqual(build(['build','.','-t','app'])['root'],Path.cwd())
 def test_context_after_tag(self):
  self.assertEqual(build(['build','-tapp','.'])['root'],Path.cwd())
 def test_global_connection(self):
  self.assertEqual(build(['--context','remote','build','.'])['prefix'],['--context','remote','build'])
 def test_builder_selection(self):
  self.assertEqual(build(['buildx','--builder','local','build','.'])['prefix'],['buildx','--builder','local','build'])
 def test_forbidden(self):
  self.assertEqual(build(['build','--network=host','.'])['forbidden'],[])
  self.assertEqual(build(['build','--pull=false','.'])['forbidden'],[])
 def test_file_alias_order(self):
  self.assertEqual(build(['build','--file','one','-ftwo','.'])['dockerfile'],Path('two').resolve())
 def test_separator(self):
  self.assertEqual(build(['build','--','.'])['root'],Path.cwd())
 def test_multiple_contexts(self):
  with self.assertRaises(ValueError):build(['build','.','other'])
if __name__=='__main__':unittest.main()
