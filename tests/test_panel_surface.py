"""Exercise the real panel primitives with isolated theme tokens and native Qt.

No Quickshell services, compositor or user preferences are loaded. Each native
Qt attempt is limited to 15 seconds, including compilation and rendering.
"""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / 'src/quickshell/modules/shared/primitives/common'


class PanelSurfaceTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 required for native offscreen QML')
    def test_variants_states_theme_geometry_and_shadow(self):
        result = subprocess.run([sys.executable, __file__, '--offscreen'],
                                capture_output=True, text=True, timeout=15)
        logs = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, logs)
        self.assertIn('PANEL_SURFACE_OK', logs)
        for error in ('ReferenceError', 'TypeError', 'Cannot assign', 'Binding loop', 'Unable to assign'):
            self.assertNotIn(error, logs)


def offscreen():
    os.environ.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QT_QPA_PLATFORMTHEME='')
    from PySide6.QtCore import QUrl, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickView

    app = QGuiApplication([])
    with tempfile.TemporaryDirectory(prefix='panel-surface-') as temporary:
        base = Path(temporary)
        shared = base / 'qs/modules/shared'
        common = shared / 'primitives/common'
        common.mkdir(parents=True)
        names = ('PanelSurface', 'PanelSurfaceShadow', 'StyledRectangularShadow')
        for name in names:
            (common / (name + '.qml')).write_text((COMMON / (name + '.qml')).read_text())
        (common / 'qmldir').write_text('module qs.modules.shared.primitives.common\n' +
                                      ''.join(f'{name} 1.0 {name}.qml\n' for name in names))
        (shared / 'qmldir').write_text('module qs.modules.shared\nsingleton Appearance 1.0 Appearance.qml\n')
        (shared / 'Appearance.qml').write_text('''pragma Singleton
import QtQuick
QtObject {
 property QtObject colors: QtObject {
  property color colLayer0Base: "#202124"
  property color colLayer0: Qt.rgba(colLayer0Base.r, colLayer0Base.g, colLayer0Base.b, .55)
  property color colLayer0Border: "#717174"
  property color colPrimary: "#b0bcff"
  property color colPrimaryContainer: "#263474"
  property color colOnPrimaryContainer: "#e0e3ff"
  property color colOnLayer0: "#eeeeee"
  property color colSubtext: "#aaaaaa"
  property color colShadow: "#50000000"
 }
 property QtObject rounding: QtObject { property real large: 24 }
 property QtObject sizes: QtObject { property real elevationMargin: 12 }
}''')
        (base / 'test.qml').write_text('''import QtQuick
import QtQuick.Layouts
import qs.modules.shared
import qs.modules.shared.primitives.common
Item {
 id: host; width: 640; height: 480
 property bool done: false
 property string failure: ""
 PanelSurfaceShadow { id: shadow; target: panel }
 PanelSurface {
  id: panel; anchors.fill: parent; anchors.margins: 20
  Item { id: content; anchors.fill: parent }
 }
 RowLayout {
  id: row; width: 240; height: 50
  PanelSurface { id: sized; implicitWidth: 80; implicitHeight: 30; Layout.fillHeight: true }
  Item { Layout.fillWidth: true }
 }
 PanelSurface { id: empty }
 function check(ok, message) { if (!ok) throw new Error(message); }
 function equal(a,b) { return String(a) === String(b); }
 Timer {
  interval: 50; running: true
  onTriggered: {
   try {
    check(panel.width === 600 && panel.height === 440 && panel.x === 20, "anchors changed");
    check(content.parent === panel && content.width === panel.width, "content reparented or padded");
    check(empty.implicitWidth === 0 && empty.implicitHeight === 0, "unexpected implicit sizing");
    check(sized.width === 80 && sized.height === 50, "layout sizing changed");
    check(panel.radius === 24 && panel.border.width === 1, "default decoration");
    check(equal(panel.color, Appearance.colors.colLayer0), "normal surface token");
    check(Math.abs(panel.color.a - .55) < .01, "translucent alpha");
    panel.variant = PanelSurface.Glass;
    check(equal(panel.color, Appearance.colors.colLayer0), "glass fallback");
    panel.variant = PanelSurface.Solid;
    check(panel.color.a === 1, "solid not opaque");
    for (const state of [PanelSurface.Normal, PanelSurface.Emphasized, PanelSurface.Selected, PanelSurface.Focused, PanelSurface.Disabled]) {
     panel.visualState = state;
     check(panel.color.a === 1, "solid state alpha");
     check(panel.width === 600 && panel.height === 440 && !panel.focus && panel.enabled, "state changed geometry/input");
     check(equal(panel.border.color, [PanelSurface.Emphasized, PanelSurface.Selected, PanelSurface.Focused].includes(state)
      ? Appearance.colors.colPrimary : Appearance.colors.colLayer0Border), "state border");
     check(equal(panel.foreground, state === PanelSurface.Selected ? Appearance.colors.colOnPrimaryContainer
      : state === PanelSurface.Disabled ? Appearance.colors.colSubtext : Appearance.colors.colOnLayer0), "state foreground");
    }
    panel.visualState = PanelSurface.Normal;
    for (const theme of ["#f8f8fa", "#17171a"]) {
     Appearance.colors.colLayer0Base = theme;
     Appearance.colors.colOnLayer0 = theme === "#f8f8fa" ? "#17171a" : "#eeeeee";
     check(equal(panel.color, Appearance.colors.colLayer0Base), "theme did not update solid");
     check(equal(panel.foreground, Appearance.colors.colOnLayer0), "theme foreground stale");
     for (const alpha of [1, .35]) {
      Appearance.colors.colLayer0 = Qt.rgba(.3,.4,.5,alpha);
      for (const variant of [PanelSurface.Translucent, PanelSurface.Glass]) {
       panel.variant = variant;
       check(equal(panel.color, Appearance.colors.colLayer0), "theme/transparency not reactive");
       panel.visualState = PanelSurface.Selected;
       check(Math.abs(panel.color.a - alpha) < .01, "selection lost transparency");
       panel.visualState = PanelSurface.Normal;
      }
      panel.variant = PanelSurface.Solid;
     }
    }
    Appearance.rounding.large = 18;
    check(panel.radius === 18 && shadow.radius === 18, "radius theme binding");
    check(shadow.width === panel.width && shadow.x === panel.x, "shadow geometry");
    check(Math.abs(shadow.blur - 10.8) < .01 && shadow.spread === 1 && shadow.offset.y === 1, "legacy shadow changed");
    shadow.elevation = 2;
    check(Math.abs(shadow.blur - 21.6) < .01 && shadow.spread === 2, "shadow elevation");
    shadow.elevation = 0;
    check(!shadow.visible, "zero elevation still visible");
    shadow.elevation = -1;
    check(!shadow.visible && shadow.blur === 0, "negative elevation");
    panel.color = "#80402010"; panel.radius = 7; panel.border.width = 3; panel.border.color = "red";
    panel.variant = PanelSurface.Translucent; panel.visualState = PanelSurface.Focused;
    check(equal(panel.color, "#80402010") && panel.radius === 7 && panel.border.width === 3 && equal(panel.border.color, "#ff0000"), "native overrides lost");
    console.log("PANEL_SURFACE_OK");
   } catch (error) { host.failure = String(error); }
   host.done = true;
  }
 }
}''')
        view = QQuickView()
        view.engine().addImportPath(str(base))
        view.setSource(QUrl.fromLocalFile(str(base / 'test.qml')))
        if view.status() == QQuickView.Error:
            raise AssertionError('\n'.join(error.toString() for error in view.errors()))
        view.show()
        timer = QTimer()
        def poll():
            root = view.rootObject()
            if root.property('done'):
                app.exit(1 if root.property('failure') else 0)
        timer.timeout.connect(poll)
        timer.start(20)
        QTimer.singleShot(10000, lambda: app.exit(2))
        status = app.exec()
        failure = view.rootObject().property('failure')
        assert status == 0, failure or 'offscreen timed out'
        view.setSource(QUrl())
        print('PANEL_SURFACE_OK')


if __name__ == '__main__':
    if '--offscreen' in sys.argv:
        offscreen()
    else:
        unittest.main()
