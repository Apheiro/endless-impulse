"""Render the real recording page offscreen with an isolated recorder/theme fixture.

No compositor, devices, capture processes or user preferences are touched.
Only the service, theme tokens and window-dependent tooltips are substituted.
"""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/quickshell'


class RecordingSettingsTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is needed for offscreen QML')
    def test_responsive_page_draft_actions_and_field_coverage(self):
        result = subprocess.run([sys.executable, __file__, '--offscreen'], text=True,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('RECORDING_SETTINGS_OK', result.stdout)
        for error in ('ReferenceError', 'TypeError', 'Cannot assign', 'Binding loop', 'Unable to assign'):
            self.assertNotIn(error, result.stderr)


def offscreen():
    os.environ.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QT_QUICK_CONTROLS_STYLE='Basic', QT_QPA_PLATFORMTHEME='')
    from PySide6.QtCore import QUrl, QPointF, QPoint, Qt, QObject
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickView
    from PySide6.QtTest import QTest
    import faulthandler
    faulthandler.dump_traceback_later(12, exit=True)
    print('Creating application', flush=True)
    app = QGuiApplication([])

    spec = importlib.util.spec_from_file_location('recording_fixture', SOURCE / 'scripts/videos/recorder.py')
    recorder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recorder)
    fields = [dict(field, supported=True) for field in recorder.FIELDS]
    values = {field['key']: field['default'] for field in fields}
    with tempfile.TemporaryDirectory(prefix='recording-settings-') as temporary:
        base = Path(temporary)
        def write(name, text):
            path = base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        def copy(name):
            write('qs/' + name, (SOURCE / name).read_text())
        for name in ('RecordingConfig.qml', 'RecorderField.qml', 'RecordingLayout.js', 'SettingsSection.qml',
                     'DesktopSettingField.qml', 'SettingsRange.qml', 'GradientColorField.qml'):
            copy('modules/settings/' + name)
        # EnvironmentPaths only imports Quickshell for its application environment;
        # its layout and controls are used unchanged in this native Qt fixture.
        name = 'modules/settings/EnvironmentPaths.qml'
        write('qs/' + name, (SOURCE / name).read_text().replace('import Quickshell\n', ''))
        copy('modules/shared/functions/GradientColors.js')
        for name in ('StyledText', 'MaterialSymbol', 'SegmentedControl', 'RippleButton', 'StyledComboBox',
                     'StyledFlickable', 'StyledScrollBar', 'MaterialTextField', 'MaterialTextArea',
                     'StyledSwitch', 'PointingHandInteraction', 'StyledRectangularShadow', 'WavyLine',
                     'StyledTextInput', 'StyledListView', 'OptionalMaterialSymbol'):
            copy('modules/shared/primitives/common/' + name + '.qml')
        name = 'modules/shared/primitives/common/StyledSlider.qml'
        write('qs/' + name, (SOURCE / name).read_text().replace('import Quickshell.Widgets\n', ''))
        copy('modules/shared/primitives/settings/SettingsCard.qml')
        copy('modules/shared/widgets/RippleButtonWithIcon.qml')
        name = 'modules/shared/functions/ColorUtils.qml'
        write('qs/' + name, (SOURCE / name).read_text().replace('import Quickshell', 'import QtQuick').replace('Singleton {', 'QtObject {'))
        write('qs/modules/shared/primitives/common/StyledToolTip.qml', 'import QtQuick\nItem { property string text; property font font; property bool extraVisibleCondition: true }')
        appearance = (SOURCE / 'modules/shared/Appearance.qml').read_text()
        m3 = dict(re.findall(r'property color (m3\w+): "(#[^"]+)"', appearance))
        colors = {key: '#24232a' for key in re.findall(r'property color (col\w+):', appearance)}
        for key in colors:
            if key.startswith('colOn') or key in ('colSubtext', 'colOutline'):
                colors[key] = '#e6e1e1'
            if 'Primary' in key and not key.startswith('colOn'):
                colors[key] = '#cbc4cb'
        colors['colOnPrimary'] = '#322f34'
        font = dict(family=dict(main='Sans', numbers='Sans', iconMaterial='Material Symbols Rounded'),
                    pixelSize=dict(small=14, smaller=12, normal=15, larger=18, huge=22),
                    variableAxes=dict(main={}, numbers={}))
        rounding = dict(small=12, normal=16, large=20, full=999, unsharpen=3, unsharpenmore=8)
        sizes = dict(elevationMargin=12, textInputHorizontalPadding=12, textInputVerticalPadding=8, textInputMinimumHeight=40)
        animation = '''property QtObject animation: QtObject {
 property QtObject elementMove:fastAnimation
 property QtObject elementMoveEnter:fastAnimation
 property QtObject elementMoveFast: QtObject { id:fastAnimation; property int duration:0; property int type:Easing.Linear; property var bezierCurve:[0,0,1,1,1,1]; property int velocity:10000; property Component numberAnimation:NumberAnimation{duration:0}; property Component colorAnimation:ColorAnimation{duration:0} }
 property QtObject scroll: QtObject {property int duration:0; property int type:Easing.Linear; property var bezierCurve:[0,0,1,1,1,1]}
}'''
        props = ''.join('property var ' + key + ':' + json.dumps(value) + '\n' for key, value in
                        dict(colors=colors, m3colors=dict(m3, darkmode=True), font=font, rounding=rounding, sizes=sizes,
                             animationCurves=dict(expressiveFastSpatialDuration=0, expressiveFastSpatial=[0,0,1,1,1,1], standardDecel=[0,0,1,1,1,1])).items())
        write('qs/modules/shared/Appearance.qml', 'pragma Singleton\nimport QtQuick\nQtObject {\n' + props + animation + '\nfunction animationDuration(ms){return 0;} }')
        write('qs/modules/shared/Config.qml', 'pragma Singleton\nimport QtQuick\nQtObject {property var options:({interactions:{scrolling:{fasterTouchpadScroll:false}}})}')
        write('qs/services/Translation.qml', 'pragma Singleton\nimport QtQuick\nQtObject {function tr(text){return text;} }')
        write('qs/services/ScreenRecorder.qml', '''pragma Singleton
import QtQuick
QtObject {
 property var fields:__FIELDS__
 property var settings:__VALUES__
 property var capabilities:({installed:true,version:"fixture",codecs:["h264"],audio:[{id:"default_output",name:"System audio"}],applications:[],capture:[{id:"DP-1"}]})
 property bool loaded:true
 property bool busy:false
 property bool active:false
 property bool paused:false
 property string elapsedText:"00:12"
 property bool failed:false
 property string message:""
 property string preview:"/tmp/recording-preview.mp4"
 property string store:"/tmp/fixture-recorder.json"
 property string statePath:"/tmp/fixture-recorder-state"
 property bool preferencesExist:true
 property int saves:0
 property int toggles:0
 property int refreshes:0
 signal preferencesSaved()
 function save(values){saves++;settings=JSON.parse(JSON.stringify(values));preferencesSaved();}
 function refresh(){refreshes++;}
 function toggle(){toggles++;active=!active;}
 function previewName(values){preview=values.filenamePattern;}
}'''.replace('__FIELDS__', json.dumps(fields)).replace('__VALUES__', json.dumps(values)))
        for directory in (base / 'qs').rglob('*'):
            if not directory.is_dir(): continue
            qml = list(directory.glob('*.qml'))
            if not qml: continue
            uri = '.'.join(directory.relative_to(base).parts)
            lines = ['module ' + uri]
            for path in qml:
                singleton = 'singleton ' if 'pragma Singleton' in path.read_text() else ''
                lines.append(singleton + path.stem + ' 1.0 ' + path.name)
            (directory / 'qmldir').write_text('\n'.join(lines))
        write('main.qml', '''import QtQuick
import qs.modules.settings
import qs.modules.shared
import qs.services
Rectangle {
 width:900;height:620;color:Appearance.colors.colLayer0
 property var recorder:ScreenRecorder
 function edit(key,value){page.put(key,value);}
 RecordingConfig{id:page;objectName:"recording-settings";anchors.fill:parent}
}''')
        print('Loading recording page', flush=True)
        view = QQuickView()
        view.engine().addImportPath(str(base))
        view.setSource(QUrl.fromLocalFile(str(base / 'main.qml')))
        assert view.status() == QQuickView.Ready, '\n'.join(str(error) for error in view.errors())
        view.setResizeMode(QQuickView.SizeRootObjectToView)
        print('Showing offscreen page', flush=True)
        view.show()
        QTest.qWait(100)
        print('Checking layout', flush=True)
        root = view.rootObject()
        page = root.findChild(QObject, 'recording-settings')
        service = root.property('recorder')
        def find(name):
            def walk(item):
                if item.objectName() == name: return item
                for child in item.childItems():
                    match = walk(child)
                    if match: return match
            return walk(page)
        def click(item):
            assert item and item.isEnabled(), 'disabled or missing button'
            point = item.mapToScene(QPointF(item.width()/2, item.height()/2))
            QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))
            QTest.qWait(50)
        assert not page.property('dirty') and service.property('saves') == 0, 'initialization writes preferences'
        for width in (360, 620, 900):
            view.resize(width, 620)
            found = set()
            for tab in range(4):
                page.setProperty('currentTab', tab)
                QTest.qWait(80)
                images = os.environ.get('DOTS_RECORDING_TEST_IMAGES')
                if images:
                    Path(images).mkdir(parents=True, exist_ok=True)
                    view.grabWindow().save(str(Path(images) / f'recording-{width}-{tab}.png'))
                if tab == 0:
                    click(find('recorder-capture-options'))
                for field in fields:
                    control = find('recorder-value-' + field['key']) or find('recorder-field-' + field['key'])
                    if control and control.isVisible():
                        found.add(field['key'])
                        position = control.mapToItem(page, QPointF(0,0))
                        assert position.x() >= 19 and position.x()+control.width() <= width-19+.5, (width, field['key'], position.x(), control.width())
                body = find('recorder-options')
                assert body.height() > 100, ('no room for options', width, body.height())
                assert not page.property('dirty'), 'tab change writes preferences'
            assert found == {field['key'] for field in fields}, ('missing controls', found ^ {field['key'] for field in fields})
        root.edit('fps', 144)
        page.setProperty('currentTab', 1)
        QTest.qWait(50)
        assert page.property('dirty') and not find('recorder-session-action').isEnabled()
        click(find('recorder-save'))
        assert not page.property('dirty') and service.property('saves') == 1
        click(find('recorder-session-action'))
        assert service.property('active')
        root.edit('quality', 'ultra')
        click(find('recorder-session-action'))
        assert not service.property('active'), 'dirty draft prevented stopping'
        click(find('recorder-discard'))
        assert not page.property('dirty')
        page.setProperty('currentTab', 2)
        QTest.qWait(50)
        editor = find('recorder-value-audioTracks')
        editor.forceActiveFocus()
        editor.setProperty('text', 'app:firefox')
        QTest.qWait(50)
        assert page.property('dirty'), 'audio editing lost'
        source = find('recorder-audio-source')
        assert source.property('currentIndex') == 0, 'audio source selection lost'
        body = find('recorder-options')
        body.setProperty('contentY', max(0, body.property('contentHeight') - body.height()))
        QTest.qWait(50)
        click(find('recorder-add-audio-track'))
        assert editor.property('text') == 'app:firefox\ndefault_output', 'selected source not added as a separate track'
        page.reset()
        QTest.qWait(50)
        assert editor.property('text') == 'default_output', 'discard did not restore focused list editor'
        print('RECORDING_SETTINGS_OK: 360/620/900 px, all schema fields, draft/save/discard/start/stop/audio')
        view.close()
        del view


if __name__ == '__main__':
    if '--offscreen' in sys.argv:
        offscreen()
    else:
        unittest.main()
