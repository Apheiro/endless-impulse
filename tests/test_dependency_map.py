"""Dependency provenance and offline map; no package-manager commands or installation."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/quickshell'
SCRIPT=SOURCE/'scripts/system/dependencies.py'
spec=importlib.util.spec_from_file_location('dependency_map',SCRIPT)
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)

class DependencyMapTests(unittest.TestCase):
    def test_declared_packages_match_manifest_once_without_retired_entries(self):
        manifest=json.loads((ROOT/'installer/dependencies/arch.json').read_text())
        data=model.build(ROOT)
        nodes=[node for group in data['groups'] for node in group['children']]
        declared=[node['package'] for node in nodes if node['declared']]
        self.assertEqual(set(declared),set(manifest['repository']+manifest['aur']))
        self.assertEqual(len(declared),len(set(declared)))
        self.assertEqual(data['total'],len(declared))
        self.assertFalse(any(node.get('retired') or node['id'].startswith(('legacy:','replaced:')) for node in nodes))
        self.assertFalse(any('illogical-impulse-' in node['title'] for node in nodes))
        self.assertTrue(all(node['description'] and node['scope'] for node in nodes))
        self.assertNotIn('bluedevil',declared);self.assertNotIn('plasma-nm',declared)
        self.assertNotIn('pavucontrol-qt',declared);self.assertNotIn('wf-recorder',declared)
    def test_committed_snapshot_matches_current_manifests_and_offline_install(self):
        snapshot=SOURCE/'defaults/dependencies.json'
        self.assertEqual(json.loads(snapshot.read_text()),model.build(ROOT))
        with tempfile.TemporaryDirectory(prefix='ai-dependency-snapshot-') as temporary:
            shell=Path(temporary)
            (shell/'scripts/system').mkdir(parents=True);(shell/'defaults').mkdir()
            shutil.copy2(SCRIPT,shell/'scripts/system/dependencies.py')
            shutil.copy2(snapshot,shell/'defaults/dependencies.json')
            result=subprocess.run([sys.executable,str(shell/'scripts/system/dependencies.py')],capture_output=True,text=True,check=True)
            data=json.loads(result.stdout)
            self.assertFalse(data['liveManifest'])
            self.assertEqual(data['total'],model.build(ROOT)['total'])
            self.assertEqual(len(data['sources']),1)
            self.assertTrue(Path(data['sources'][0]['path']).is_file())
    def test_checkout_provenance_points_only_to_existing_files(self):
        data=json.loads(subprocess.check_output([sys.executable,str(SCRIPT)],text=True))
        self.assertTrue(data['liveManifest'])
        self.assertTrue(all(Path(source['path']).is_file() for source in data['sources']))
        self.assertIn(str(ROOT/'packaging/nix/package.nix'),[item['path'] for item in data['sources']])
