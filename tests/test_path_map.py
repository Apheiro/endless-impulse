"""Path catalog metadata and tree navigation; no personal file contents are read."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/quickshell"
spec = importlib.util.spec_from_file_location("path_map", SOURCE / "scripts/shell/path_map.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def record(path, title="Folder", group="config", **extra):
    return dict(path=str(path), title=title, description="Desktop preferences", group=group, groupTitle=group, groupIcon="folder", tags=[], **extra)


class PathMapTests(unittest.TestCase):
    def test_nearest_parent_and_unique_paths_merge_shared_uses(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "custom config"
            records = [record(folder / "config.json", "Preferences", kind="file"), record(folder),
                       record(folder / "icons", "Icons"),
                       dict(record(folder / "icons", "Toolkit icons", group="data"), description="Used by GTK and Qt", tags=["GTK", "Qt"])]
            groups = catalog.build(records)
            self.assertEqual(len(groups), 1)
            parent = groups[0]["children"][0]
            self.assertEqual(parent["path"], str(folder))
            self.assertEqual(len(parent["children"]), 2)
            icons = parent["children"][1]
            self.assertEqual(icons["tags"], ["GTK", "Qt"])
            self.assertEqual(icons["uses"], ["Desktop preferences", "Used by GTK and Qt"])
            self.assertFalse(folder.exists())

    def test_actual_symlink_destination_and_unavailable_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            real = base / "checkout"
            real.mkdir()
            link = base / "interface"
            link.symlink_to(real, target_is_directory=True)
            children = catalog.build([record(link), record(base / "not-created")])[0]["children"]
            self.assertTrue(children[0]["exists"])
            self.assertEqual(children[0]["target"], str(real))
            self.assertEqual(children[0]["path"], str(link))
            self.assertFalse(children[1]["exists"])
            self.assertFalse((base / "not-created").exists())

    def test_file_urls_special_characters_and_normalization(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "icons #1 ñ"
            path.mkdir()
            groups = catalog.build([record(path.as_uri()), record(path / ".." / path.name)])
            self.assertEqual(len(groups[0]["children"]), 1)
            self.assertEqual(groups[0]["children"][0]["path"], str(path))
            self.assertTrue(groups[0]["children"][0]["exists"])

    def test_files_never_become_parent_directories_and_groups_remain_distinct(self):
        groups = catalog.build([record("/custom/a", kind="file"), record("/custom/a/b"), record("/custom/c", group="data")])
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups[0]["children"]), 2)
        self.assertEqual(groups[1]["children"][0]["path"], "/custom/c")

    def test_relative_paths_are_rejected_and_empty_destinations_are_omitted(self):
        self.assertEqual(catalog.build([record("")]), [])
        with self.assertRaises(ValueError):
            catalog.build([record("relative/path")])

    @unittest.skipUnless(shutil.which("node"), "Node is needed for tree navigation checks")
    def test_search_expansion_and_collapse_preserve_hierarchy(self):
        script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8').replace(/^\.pragma library\s*/, ''), context);
const leaf = (id, title, tags=[]) => ({id, title, path:'/custom/'+id, tags, uses:[], children:[]});
const groups = [{id:'group:config', title:'Configuración', path:'', children:[
  {...leaf('gtk','GTK'), children:[leaf('icons','Icons',['GTK','Qt'])]}, leaf('hypr','Hyprland')
]}, {id:'group:data', title:'Local data', path:'', children:[leaf('cache','Cache')]}];
const ids = rows => Array.from(rows, row => row.node.id).join(',');
assert.equal(context.count(groups), 4);
assert.equal(ids(context.flatten(groups, {}, '')), 'group:config,group:data');
assert.equal(ids(context.flatten(groups, {'group:config':true}, '')), 'group:config,gtk,hypr,group:data');
const filtered = context.flatten(groups, {}, 'icons qt');
assert.equal(ids(filtered), 'group:config,gtk,icons');
assert.equal(filtered[2].depth, 2);
assert.equal(ids(context.flatten(groups, {}, 'configuracion')), 'group:config,gtk,icons,hypr');
assert.equal(context.flatten(groups, {}, 'nothing').length, 0);
assert.equal(groups[0].children.length, 2);
assert.equal(context.flatten(groups, {}, '').length, 2);
'''
        result = subprocess.run([shutil.which("node"), "-e", script, str(SOURCE / "modules/shared/functions/PathTree.js")], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
