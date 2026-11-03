"""Native DesktopEntries rescans, using disposable XDG directories and no desktop UI.

Run through ./dev check -p test_app_search.py so Qt and Quickshell use the Nix runtime.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/quickshell'


@unittest.skipUnless(os.environ.get('DOTS_TEST_LAUNCHER'), 'Run with ./dev check (Nix Qt runtime)')
class AppSearchTests(unittest.TestCase):
    def test_completed_catalog_and_live_search(self):
        with tempfile.TemporaryDirectory(prefix='ai-app-search-') as temporary:
            base = Path(temporary)
            services = base / 'services'
            shared = base / 'modules/shared'
            functions = shared / 'functions'
            services.mkdir()
            functions.mkdir(parents=True)
            for name in ('AppSearch.qml', 'LauncherSearch.qml'):
                shutil.copy2(SOURCE / 'services' / name, services)
            models = shared / 'models'
            models.mkdir()
            shutil.copy2(SOURCE / 'modules/shared/models/LauncherSearchResult.qml', models)
            for name in ('Fuzzy.qml', 'fuzzysort.js', 'Levendist.qml', 'levendist.js', 'StringUtils.qml'):
                shutil.copy2(SOURCE / 'modules/shared/functions' / name, functions)
            # AppSearch's unrelated preferences/icon theme dependencies are isolated.
            (shared / 'Config.qml').write_text('''pragma Singleton
import Quickshell
Singleton { property var options: ({
    search: {sloppy: false, nonAppResultDelay: 1000, prefix: {
        app: "!", action: ">", clipboard: ":", emojis: ";", math: "=",
        shellCommand: "$", webSearch: "?", showDefaultActionsWithoutPrefix: false}},
    workSafety: {enable: {clipboard: false}, triggerCondition: {networkNameKeywords: []}}
}) }
''')
            (services / 'IconTheme.qml').write_text('''pragma Singleton
import Quickshell
Singleton {
    property var aliases: ({"test-alias": "test-icon"})
    function iconPath(name, fallback) { return Quickshell.iconPath(name, fallback); }
}
''')
            for name, body in {
                'Network': 'property string networkName: ""',
                'Directories': 'property string userActions: "' + (base / 'actions').as_uri() + '"',
                'Translation': 'function tr(text) { return text; }',
            }.items():
                (services / (name + '.qml')).write_text('pragma Singleton\nimport Quickshell\nSingleton { ' + body + ' }\n')
            (base / 'actions').mkdir()
            (base / 'shell.qml').write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import qs.services
ShellRoot {
    id: root
    property int publications: 0
    property int modelChanges: 0
    property int completions: 0
    Connections {
        target: AppSearch
        function onListChanged() { root.publications++; }
    }
    Connections {
        target: DesktopEntries.applications
        function onValuesChanged() { root.modelChanges++; }
    }
    Connections {
        target: DesktopEntries
        function onApplicationsChanged() { root.completions++; }
    }
    IpcHandler {
        target: "test"
        function state(): string {
            return JSON.stringify({publications: root.publications,
                modelChanges: root.modelChanges, completions: root.completions,
                names: AppSearch.preppedNames.length, icons: AppSearch.preppedIcons.length,
                categories: LauncherSearch.appCategories,
                entries: AppSearch.list.map(e => ({id: e.id, name: e.name, icon: e.icon,
                    categories: e.categories, command: e.command, keywords: e.keywords,
                    actions: e.actions.map(a => a.name)}))});
        }
        function search(query: string, sloppy: bool): string {
            AppSearch.sloppySearch = sloppy;
            return JSON.stringify(AppSearch.fuzzyQuery(query).map(e => e.id));
        }
        function launcher(query: string): string {
            LauncherSearch.query = query;
            return JSON.stringify(LauncherSearch.results.map(r => ({id: r.id, name: r.name,
                actions: r.actions.map(a => a.name)})));
        }
        function icon(query: string): string { return AppSearch.guessIcon(query); }
        function execute(id: string): void {
            const entry = AppSearch.list.find(e => e.id === id);
            entry.execute();
        }
    }
}
''')
            high, low = base / 'high/applications', base / 'low/applications'
            high.mkdir(parents=True)
            low.mkdir(parents=True)
            marker = base / 'executed'

            def desktop(path, name, extra=''):
                # Atomic install/update, as package managers and desktop file editors do.
                pending = path.with_suffix('.pending')
                pending.write_text('[Desktop Entry]\nType=Application\n'
                                   f'Name={name}\nExec=touch {marker}\nIcon=utilities-terminal\n'
                                   'Categories=Utility;Development;\nKeywords=fixture;\n' + extra)
                pending.replace(path)

            for i in range(320):
                desktop(low / f'fixture-{i}.desktop', f'Fixture Application {i}')
            desktop(high / 'fixture-0.desktop', 'Priority App')
            desktop(high / 'masked.desktop', 'Masked', 'Hidden=true\n')
            desktop(low / 'masked.desktop', 'Must be masked')
            desktop(high / 'nodisplay.desktop', 'Not searchable', 'NoDisplay=true\n')
            env = dict(os.environ, DOTS_SHELL_SOURCE=str(base), QT_QPA_PLATFORM='offscreen',
                       XDG_CONFIG_HOME=str(base / 'config'), XDG_STATE_HOME=str(base / 'state'),
                       XDG_CACHE_HOME=str(base / 'cache'), XDG_DATA_HOME=str(high.parent),
                       XDG_DATA_DIRS=f'{low.parent}:{low.parent}')
            # The outer Qt wrapper adds runtime data paths; putting this fixture first
            # in XDG_DATA_HOME preserves its priority without changing host preferences.
            logpath = base / 'shell.log'
            with logpath.open('w') as log:
                proc = subprocess.Popen([env['DOTS_TEST_LAUNCHER'], '--no-duplicate'],
                                        env=env, stdout=log, stderr=log)
                try:
                    command = [env['DOTS_TEST_LAUNCHER']]

                    def ipc(function, *args):
                        result = subprocess.run(command + ['ipc', 'call', 'test', function, *map(str, args)],
                                                env=env, capture_output=True, text=True, timeout=3)
                        if result.returncode or not result.stdout.strip():
                            raise RuntimeError(result.stdout + result.stderr)
                        return result.stdout.strip()

                    def wait_state(predicate):
                        deadline = time.monotonic() + 12
                        last = None
                        while time.monotonic() < deadline:
                            self.assertIsNone(proc.poll(), logpath.read_text())
                            try:
                                last = json.loads(ipc('state'))
                                if predicate(last):
                                    return last
                            except (RuntimeError, json.JSONDecodeError):
                                pass
                            time.sleep(.08)
                        self.fail(f'Catalog did not settle: {last}\n{logpath.read_text()}')

                    def entries(state):
                        return {entry['id']: entry for entry in state['entries']}

                    initial = wait_state(lambda s: entries(s).get('fixture-0', {}).get('name') == 'Priority App')
                    self.assertIn('Utility', initial['categories'])
                    self.assertIn('Development', initial['categories'])
                    self.assertNotIn('masked', entries(initial))
                    self.assertNotIn('nodisplay', entries(initial))
                    self.assertEqual(len(entries(initial)), len(initial['entries']))
                    self.assertEqual(initial['names'], len(initial['entries']))
                    self.assertEqual(initial['icons'], len(initial['entries']))
                    self.assertIn('fixture-0', json.loads(ipc('search', 'Priority App', 'false')))
                    self.assertIn('fixture-0', json.loads(ipc('search', 'Priority App', 'true')))
                    launched = json.loads(ipc('launcher', '!Priority App'))
                    self.assertIn('fixture-0', [r['id'] for r in launched])
                    self.assertEqual(ipc('icon', 'fixture-0'), 'utilities-terminal')
                    self.assertEqual(ipc('icon', 'test-alias'), 'test-icon')
                    self.assertEqual(ipc('icon', 'steam_app_42'), 'steam_icon_42')

                    # Recreate the unchanged-catalog rescan from the real launch traces.
                    # Repeated XDG paths force many row replacements in Quickshell 0.3.2.
                    before = wait_state(lambda s: s['completions'] > 0)
                    trigger = low.parent / 'unrelated'
                    trigger.mkdir()
                    after = wait_state(lambda s: s['completions'] > before['completions'])
                    self.assertGreater(after['modelChanges'] - before['modelChanges'], 100)
                    self.assertEqual(after['publications'] - before['publications'],
                                     after['completions'] - before['completions'])
                    self.assertEqual(entries(before), entries(after))

                    desktop(high / 'fixture-0.desktop', 'Renamed App',
                            'Icon=application-x-executable\nCategories=Network;\nKeywords=updated;\n'
                            'Actions=Test;\n[Desktop Action Test]\nName=Test Action\nExec=true\n')
                    changed = wait_state(lambda s: entries(s).get('fixture-0', {}).get('name') == 'Renamed App')
                    updated = entries(changed)['fixture-0']
                    self.assertEqual(updated['categories'], ['Network'])
                    self.assertIn('Network', changed['categories'])
                    launched = json.loads(ipc('launcher', '!Renamed App'))
                    self.assertEqual(next(r for r in launched if r['id'] == 'fixture-0')['actions'], ['Test Action'])
                    self.assertEqual(updated['keywords'], ['updated'])
                    self.assertEqual(updated['actions'], ['Test Action'])
                    self.assertEqual(ipc('icon', 'fixture-0'), 'application-x-executable')
                    self.assertIn('fixture-0', json.loads(ipc('search', 'Renamed App', 'false')))
                    self.assertNotIn('fixture-0', json.loads(ipc('search', 'Priority App', 'false')))
                    subprocess.run(command + ['ipc', 'call', 'test', 'execute', 'fixture-0'],
                                   env=env, check=True, capture_output=True, timeout=3)
                    deadline = time.monotonic() + 3
                    while not marker.exists() and time.monotonic() < deadline:
                        time.sleep(.03)
                    self.assertTrue(marker.exists(), 'DesktopEntry.execute() lost its native object')

                    desktop(high / 'new.desktop', 'Newly Installed')
                    wait_state(lambda s: 'new' in entries(s))
                    (high / 'new.desktop').unlink()
                    wait_state(lambda s: 'new' not in entries(s))
                    (high / 'fixture-0.desktop').unlink()
                    wait_state(lambda s: entries(s).get('fixture-0', {}).get('name') == 'Fixture Application 0')
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
            logs = logpath.read_text()
            for error in ('TypeError:', 'ReferenceError:', 'Cannot assign', 'Unable to assign', 'Binding loop'):
                self.assertNotIn(error, logs)
