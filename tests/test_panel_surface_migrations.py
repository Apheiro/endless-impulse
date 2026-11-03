"""Surface contracts: real migrated headers offscreen, plus window-owned refs.

Only the background declarations are instantiated; feature content/services and
Wayland interaction remain covered by the existing session integration tests.
"""
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / 'src/quickshell/modules'
SURFACES = {
    'desktop/bar/ConfiguredBarContent.qml': ('drawer', None),
    'desktop/bar/BarContent.qml': ('contextBackground',),
    'desktop/bar/LegacyBarContent.qml': ('barBackground',),
    'desktop/verticalBar/VerticalBarContent.qml': ('barBackground',),
    'desktop/bar/StyledPopup.qml': ('popupBackground',),
    'desktop/bar/RecordingButton.qml': ('popupBackground',),
    'desktop/bar/SysTrayMenu.qml': ('popupBackground',),
    'desktop/cheatsheet/Cheatsheet.qml': ('cheatsheetBackground',),
    'desktop/wallpaperSelector/WallpaperSelectorContent.qml': ('wallpaperGridBackground',),
    'desktop/onScreenKeyboard/OnScreenKeyboard.qml': ('oskBackground',),
    'desktop/mediaControls/MediaControls.qml': ('placeholderBackground',),
    'desktop/onScreenDisplay/OsdValueIndicator.qml': ('valueIndicator',),
    'desktop/overview/OverviewWidget.qml': ('overviewBackground',),
    'desktop/overview/SearchWidget.qml': ('searchWidgetContent',),
    'desktop/dock/DockApps.qml': ('popupBackground',),
    'desktop/overlay/OverlayTaskbar.qml': ('root',),
    'shared/primitives/dialogs/WindowDialog.qml': ('dialogBackground',),
    'shared/widgets/SelectionDialog.qml': ('dialog',),
    'desktop/sidebarRight/todo/TodoWidget.qml': ('dialog',),
}
# Ignore quoted braces and comments when locating native QML object boundaries.
TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`|//[^\n]*|/\*[\s\S]*?\*/|[{}]')


def surface_header(path, name, *, trim=True):
    text = (MODULES / path).read_text()
    for match in re.finditer(r'PanelSurface\s*{', text):
        depth = 0
        for token in TOKENS.finditer(text, match.end() - 1):
            if token.group() == '{':
                depth += 1
            elif token.group() == '}':
                depth -= 1
                if depth == 0:
                    block = text[match.start():token.end()]
                    break
        if name is None:
            selected = 'x: root.outerMargin' in block
        else:
            selected = bool(re.search(r'\bid:\s*' + name + r'\b', block))
        if selected:
            if not trim:
                return block
            # Preserve the original decoration/geometry declarations and anchors;
            # exclude content and animations that require the feature services.
            stop = re.search(r'\n[ \t]*(?:ColumnLayout|RowLayout|Column|StackView|Behavior|Keys\.|function\s)', block)
            return block[:stop.start()] + '\n}' if stop else block
    raise AssertionError(f'Missing migrated surface: {path}:{name}')


class MigrationContracts(unittest.TestCase):
    def test_custom_colors_and_borderless_surfaces_keep_their_policy(self):
        for path, name in (
            ('desktop/onScreenKeyboard/OnScreenKeyboard.qml', 'oskBackground'),
            ('desktop/mediaControls/MediaControls.qml', 'placeholderBackground'),
            ('desktop/onScreenDisplay/OsdValueIndicator.qml', 'valueIndicator'),
            ('desktop/overview/OverviewWidget.qml', 'overviewBackground'),
            ('desktop/overview/SearchWidget.qml', 'searchWidgetContent'),
            ('desktop/dock/DockApps.qml', 'popupBackground'),
            ('shared/primitives/dialogs/WindowDialog.qml', 'dialogBackground'),
            ('shared/widgets/SelectionDialog.qml', 'dialog'),
            ('desktop/sidebarRight/todo/TodoWidget.qml', 'dialog'),
        ):
            with self.subTest(path=path):
                self.assertIn('border.width: 0', surface_header(path, name))
        for path, name, token in (
            ('desktop/bar/StyledPopup.qml', 'popupBackground', 'Appearance.m3colors.m3surfaceContainer'),
            ('desktop/dock/DockApps.qml', 'popupBackground', 'Appearance.m3colors.m3surfaceContainer'),
            ('desktop/overview/OverviewWidget.qml', 'overviewBackground', 'Appearance.colors.colBackgroundSurfaceContainer'),
            ('desktop/overview/SearchWidget.qml', 'searchWidgetContent', 'Appearance.colors.colBackgroundSurfaceContainer'),
            ('desktop/overlay/OverlayTaskbar.qml', 'root', 'Appearance.m3colors.m3surfaceContainer'),
            ('shared/primitives/dialogs/WindowDialog.qml', 'dialogBackground', 'Appearance.m3colors.m3surfaceContainerHigh'),
            ('shared/widgets/SelectionDialog.qml', 'dialog', 'Appearance.m3colors.m3surfaceContainerHigh'),
            ('desktop/sidebarRight/todo/TodoWidget.qml', 'dialog', 'Appearance.m3colors.m3surfaceContainerHigh'),
        ):
            with self.subTest(path=path):
                self.assertIn('color: ' + token, surface_header(path, name, trim=False))

    def test_window_owned_masks_focus_aliases_and_animation_refs(self):
        contracts = {
            'desktop/bar/BarContent.qml': ['contextSurface:context.visible?contextBackground:null', 'editorSurface:editing?(configured.item?.editorSurface??null):null', 'Keys.onEscapePressed:', 'root.forceActiveFocus()'],
            'desktop/bar/ConfiguredBarContent.qml': ['editorSurface: drawer', 'objectName:"bar-editor-drawer"', 'visible:root.editing', 'ShaderEffectSource', 'BarLayout.save()', 'BarLayout.cancel()'],
            'desktop/bar/Bar.qml': ['item: barContent.editorSurface', 'item: barContent.contextSurface'],
            'desktop/bar/StyledPopup.qml': ['default property Item contentItem', 'children: [root.contentItem]', 'item: popupBackground', 'target: popupBackground'],
            'desktop/bar/RecordingButton.qml': ['mask: Region { item: popupBackground }', 'objectName: "recording-menu-surface"', 'item: root', 'menu.anchor.updateAnchor()', 'ScreenRecorder.start(', 'ScreenRecorder.pause()', 'ScreenRecorder.stop()'],
            'desktop/bar/SysTrayMenu.qml': ['opacity: popupBackground.opacity', 'clip: true', 'Behavior on implicitWidth', 'Behavior on implicitHeight', 'stackView.pop()', 'root.menuClosed()'],
            'desktop/cheatsheet/Cheatsheet.qml': ['item: cheatsheetBackground', 'target: cheatsheetBackground', 'Keys.onPressed:'],
            'desktop/onScreenKeyboard/OnScreenKeyboard.qml': ['item: oskBackground', 'target: oskBackground', 'Keys.onPressed:'],
            'desktop/wallpaperSelector/WallpaperSelectorContent.qml': ['focus: true', 'target: wallpaperGridBackground', 'Keys.onPressed:'],
            'desktop/overview/SearchWidget.qml': ['width: searchWidgetContent.width', 'radius: searchWidgetContent.radius', 'layer.effect: OpacityMask', 'Behavior on implicitHeight'],
        }
        for path, needles in contracts.items():
            with self.subTest(path=path):
                text = (MODULES/path).read_text()
                for needle in needles:
                    self.assertIn(needle, text)
        for path in ('desktop/bar/LegacyBarContent.qml', 'desktop/verticalBar/VerticalBarContent.qml'):
            text = (MODULES/path).read_text()
            self.assertIn('anchors.fill: undefined', text)
            self.assertIn('sourceComponent: StyledRectangularShadow', text)
            self.assertIn('Config.options.bar.showBackground && Config.options.bar.cornerStyle === 1', text)

    @unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 required')
    def test_real_background_bindings_offscreen(self):
        result = subprocess.run([sys.executable, __file__, '--offscreen'],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('MIGRATED_SURFACES_OK 20', result.stdout)
        for error in ('ReferenceError', 'TypeError', 'Binding loop', 'Unable to assign', 'Cannot assign'):
            self.assertNotIn(error, result.stderr)

    @unittest.skipUnless(Path('/usr/lib/qt6/bin/qmlformat').exists(), 'Qt 6 qmlformat required')
    def test_qt6_parse_all_migrated_consumers(self):
        paths = [str(MODULES / path) for path in SURFACES]
        paths += [str(MODULES/'shared/primitives/common/PanelSurface.qml'),
                  str(MODULES/'shared/primitives/common/PanelSurfaceShadow.qml')]
        result = subprocess.run(['/usr/lib/qt6/bin/qmlformat', '-n', *paths],
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


def offscreen():
    os.environ.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QT_QPA_PLATFORMTHEME='')
    from PySide6.QtCore import QUrl, qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    app = QGuiApplication([])
    messages = []
    qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    with tempfile.TemporaryDirectory(prefix='migrated-panels-') as temporary:
        base = Path(temporary)
        shared = base/'qs/modules/shared'
        common = shared/'primitives/common'
        common.mkdir(parents=True)
        shutil.copy(MODULES/'shared/primitives/common/PanelSurface.qml', common)
        (common/'qmldir').write_text('module qs.modules.shared.primitives.common\nPanelSurface 1.0 PanelSurface.qml\n')
        (shared/'qmldir').write_text('module qs.modules.shared\nsingleton Appearance 1.0 Appearance.qml\nsingleton Config 1.0 Config.qml\n')
        (shared/'Appearance.qml').write_text('''pragma Singleton
import QtQuick
QtObject {
 property QtObject colors: QtObject {
  property color colLayer0Base: "#242424"
  property color colLayer0: "#88242424"
  property color colLayer0Border: "#888888"
  property color colOnLayer0: "white"
  property color colPrimary: "blue"
  property color colPrimaryContainer: "navy"
  property color colOnPrimaryContainer: "white"
  property color colSubtext: "gray"
 }
 property QtObject m3colors: QtObject { property color m3surfaceContainer: "#333333" }
 property QtObject rounding: QtObject { property real small: 8; property real large: 24; property real windowRounding: 16 }
 property QtObject sizes: QtObject { property real elevationMargin: 12; property real hyprlandGapsOut: 4 }
}''')
        (shared/'Config.qml').write_text('''pragma Singleton
import QtQuick
QtObject {
 property QtObject options: QtObject {
  property QtObject bar: QtObject {
   property bool showBackground: true
   property int cornerStyle: 1
   property bool bottom: false
   property bool vertical: false
  }
 }
}''')
        engine = QQmlEngine()
        engine.addImportPath(str(base))
        count = 0
        # Critical bar/menu surfaces run as their real native QML declarations,
        # with minimal content measurements instead of devices or feature logic.
        for path in list(SURFACES)[:7]:
            for name in SURFACES[path]:
                header = surface_header(path, name)
                checks = '''function check(ok,msg) { if (!ok) throw new Error(msg); }
 function verify() {
  check(target.width >= 0 && target.height >= 0, "negative geometry");
  check(target.border.width === 1, "default border changed");
'''
                if name is None or path.endswith(('LegacyBarContent.qml', 'VerticalBarContent.qml')):
                    checks += '''
  check(String(target.color) === String(Appearance.colors.colLayer0), "bar background token");
  Config.options.bar.showBackground = false;
  check(target.color.a === 0, "showBackground ignored");
  Config.options.bar.cornerStyle = 0;
  check(target.radius === 0 && target.border.width === 0, "square bar changed");
  Config.options.bar.cornerStyle = 1; Config.options.bar.showBackground = true;
'''
                elif name == 'drawer':
                    checks += '''
  check(target.objectName === "bar-editor-drawer" && target.visible, "editor identity/visibility");
  check(target.width === 976 && target.height === 220, "drawer geometry");
  check(target.y === 54, "top drawer position");
  Config.options.bar.bottom = true;
  check(target.y === 20, "bottom drawer position");
  root.editing = false; check(!target.visible, "editor stays visible");
  Config.options.bar.bottom = false;
'''
                elif path.endswith('StyledPopup.qml'):
                    checks += '''
  check(target.color.a === 1 && String(target.color) === String(Appearance.m3colors.m3surfaceContainer), "opaque popup color lost");
  check(target.implicitWidth === 90 && target.implicitHeight === 50, "popup content measurement");
  check(target.children[0] === root.contentItem, "default content reparenting");
'''
                elif path.endswith('RecordingButton.qml'):
                    checks += '''
  check(target.objectName === "recording-menu-surface", "recording identity");
  check(target.x === 12 && target.y === 12 && target.width === 976 && target.height === 576, "recording margin");
'''
                elif path.endswith('SysTrayMenu.qml'):
                    checks += '''
  check(target.clip && target.opacity === 1, "tray fade/clip defaults");
  check(target.implicitWidth === 128 && target.implicitHeight === 68, "tray nested content sizing");
  check(target.y === 12, "tray top anchor");
  Config.options.bar.bottom = true;
  check(target.y === 520, "tray bottom anchor");
  Config.options.bar.vertical = true;
'''
                checks += '\n }'
                checks += '''
 function restoreConfig() {
  Config.options.bar.bottom = false; Config.options.bar.vertical = false;
 }
'''
                # Bind through the actual ID to guard references used by masks.
                surface_id = name or 'testedBar'
                if name is None:
                    header = header.replace('PanelSurface {', 'PanelSurface { id: testedBar;', 1)
                source = '''import QtQuick
import qs.modules.shared
import qs.modules.shared.primitives.common
Item {
 id: root; width: 1000; height: 600
 component OriginalSurface: Rectangle {
  color: Appearance.colors.colLayer0
  radius: Appearance.rounding.large
  border.width: 1
  border.color: Appearance.colors.colLayer0Border
 }
 property var target: ''' + surface_id + '''
 property bool editing: true
 property real outerMargin: 4
 property real barHeight: 50
 property real drawerHeight: 220
 property real padding: 12
 property real popupBackgroundMargin: 3
 property Item contentItem: Item { implicitWidth: 70; implicitHeight: 30 }
 Item { id: strip; height: 50 }
 QtObject { id: menu; property real shadowMargin: 12 }
 QtObject { id: stackView; property real implicitWidth: 120; property real implicitHeight: 60 }
 QtObject { id: popupWindow; property QtObject anchors: QtObject { property bool left: true; property bool right: false; property bool top: true; property bool bottom: false } }
''' + header + '\n' + checks + '\n}'
                snapshots = []
                # Compare against native Rectangle with the original repeated
                # decoration. Anchor transitions must preserve native behavior,
                # including Qt's retained height when switching anchor sets.
                for candidate in (source, source.replace(header, header.replace('PanelSurface', 'OriginalSurface', 1))):
                    component = QQmlComponent(engine)
                    component.setData(candidate.encode(), QUrl.fromLocalFile(str(base/'fixture.qml')))
                    obj = component.create()
                    assert obj is not None, f'{path}:{name}\n' + '\n'.join(e.toString() for e in component.errors())
                    app.processEvents()
                    from PySide6.QtCore import QMetaObject
                    assert QMetaObject.invokeMethod(obj, 'verify'), f'verification failed {path}:{name}'
                    app.processEvents()
                    target = obj.property('target')
                    snapshots.append(tuple(target.property(key) for key in
                                           ('x', 'y', 'width', 'height', 'implicitWidth', 'implicitHeight', 'radius', 'color', 'clip', 'opacity')))
                    assert not messages, f'{path}:{name}: ' + '\n'.join(messages)
                    QMetaObject.invokeMethod(obj, 'restoreConfig')
                    obj.deleteLater()
                    app.processEvents()
                assert snapshots[0] == snapshots[1], f'{path}:{name}: native geometry/style changed: {snapshots}'
        # Every inventoried migration must still expose the exact background ID.
        for path, names in SURFACES.items():
            for name in names:
                surface_header(path, name)
                count += 1
        print(f'MIGRATED_SURFACES_OK {count}')


if __name__ == '__main__':
    if '--offscreen' in sys.argv:
        offscreen()
    else:
        unittest.main()
