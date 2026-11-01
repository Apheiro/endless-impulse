"""Check the shared key labels and category filtering used by both shortcut views."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src/quickshell/modules/shared/functions/ShortcutSymbols.js"


@unittest.skipUnless(shutil.which("node"), "Node is needed for the shared JavaScript checks")
class ShortcutSymbolTests(unittest.TestCase):
    def test_shared_icons_exact_keys_and_category_search(self):
        script = r'''
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8').replace(/^\.pragma library\s*/, ''), context);
const options = {superKey: '⌘', useMacSymbol: true, useFnSymbol: true, useMouseSymbol: true, splitButtons: true};
const labels = input => Array.from(context.tokens(input, options), item => item.text);
assert.deepEqual(labels('CTRL + SUPER + F1'), ['󰘴', '⌘', '+', '󱊫']);
assert.deepEqual(labels('SUPER + mouse:272'), ['⌘', '+', 'L󰍽']);
assert.deepEqual(labels('SUPER + code:11'), ['⌘', '+', 'code:11']);
assert.deepEqual(labels('SUPER_L'), ['⌘ L']);
assert.deepEqual(labels('XF86AudioMute'), ['󰝟']);
options.splitButtons = false;
assert.deepEqual(labels('CTRL + SUPER + Return'), ['󰘴 ⌘', '+', '󰌑']);
options.useMacSymbol = false;
options.useFnSymbol = false;
options.useMouseSymbol = false;
assert.deepEqual(labels('CTRL + Return'), ['Ctrl', '+', 'Enter']);
assert.deepEqual(labels('F12'), ['F12']);
const entries = [
    {category:'Shell', description:'Shell: Overview', current:'SUPER + Tab', default:'SUPER + Tab', submap:''},
    {category:'Workspace', description:'', current:'SUPER + code:11', default:'SUPER + code:11', submap:''},
    {description:'Window: Focus', current:'SUPER + F1', default:'SUPER + F1', submap:''}
];
assert.equal(context.groups(entries, '').reduce((count, group) => count + group.entries.length, 0), 3);
assert.equal(context.groups(entries, 'workspace code:11')[0].entries[0].current, 'SUPER + code:11');
assert.equal(context.groups(entries, 'window')[0].name, 'Window');
assert.equal(context.groups(entries, 'missing').length, 0);
assert.equal(context.description(entries[0]), 'Overview');
assert.equal(context.description(entries[1]), 'SUPER + code:11');
'''
        result = subprocess.run([shutil.which("node"), "-e", script, str(SCRIPT)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
