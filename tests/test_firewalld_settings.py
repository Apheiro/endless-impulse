"""Render the real firewall page and shared controls with isolated Qt/service fixtures.
No D-Bus connection or host command is available to this fixture.
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


class FirewallSettingsTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 required for isolated QML')
    def test_responsive_states_forms_and_confirmation(self):
        result = subprocess.run([sys.executable, __file__, '--offscreen'], capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('FIREWALL_SETTINGS_OK', result.stdout)
        for error in ('ReferenceError', 'TypeError', 'Cannot assign', 'Binding loop', 'Unable to assign'):
            self.assertNotIn(error, result.stderr)


def offscreen():
    os.environ.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QT_QUICK_CONTROLS_STYLE='Basic', QT_QPA_PLATFORMTHEME='')
    from PySide6.QtCore import QUrl, QObject, QPointF, QPoint, Qt
    from PySide6.QtGui import QGuiApplication, QColor
    from PySide6.QtQuick import QQuickView
    from PySide6.QtTest import QTest
    app = QGuiApplication([])
    with tempfile.TemporaryDirectory(prefix='firewall-settings-') as temporary:
        base = Path(temporary)
        def write(name, text):
            path = base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        def copy(name):
            write('qs/' + name, (SOURCE / name).read_text())
        copy('modules/settings/FirewallConfig.qml')
        for name in ('StyledText', 'MaterialSymbol', 'RippleButton', 'SegmentedControl', 'MaterialTextField',
                     'StyledComboBox', 'StyledFlickable', 'StyledScrollBar', 'StateLayer', 'StyledTextInput',
                     'PointingHandInteraction', 'StyledListView', 'OptionalMaterialSymbol', 'StyledRectangularShadow'):
            copy('modules/shared/primitives/common/' + name + '.qml')
        copy('modules/shared/primitives/settings/SettingsCard.qml')
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
        write('qs/services/FirewalldControl.qml', """pragma Singleton
import QtQuick
QtObject {
 property bool active: false
 property bool busy: false
 property bool refreshing: false
 property var snapshot: ({connected:true,complete:true,state:"connected",defaultZone:"home",revision:"test",
    connections:[{interface:"fixture0",name:"Fixture network",type:"wifi",status:"connected",zone:"home",binding:"explicit",permanentZone:"",primary:true,manager:"Unknown",canAssign:true},
                 {interface:"fixture1",name:"Second network",type:"ethernet",status:"disconnected",zone:"trusted",binding:"default",primary:false,manager:"NetworkManager",canAssign:false}],
    capabilities:["new-zone","new-service","new-ipset","change-interface","info-service","info-ipset","info-zone","add-protocol","remove-protocol","add-port","remove-port"],
    catalogs:{runtime:{services:["ssh","http"],ipsets:["fixture-set"],icmptypes:["echo-request"]},permanent:{services:["ssh","http"],ipsets:[],icmptypes:[]}},
    services:["ssh","http"],differences:["home"],activeZones:[{name:"home",active:true,fields:{interfaces:"fixture0",sources:"192.0.2.0/24",target:"default"}}],
    scopes:{runtime:{zones:[{name:"home",active:true,fields:{target:"default",interfaces:"fixture0",sources:"192.0.2.0/24",services:"ssh",ports:"8080/tcp",forward:"yes",masquerade:"no","rich rules":"rule family=ipv6 source address=2001:db8::/32 accept"}},{name:"trusted",active:false,fields:{target:"ACCEPT"}}],policies:[{name:"fixture-policy",active:true,fields:{target:"CONTINUE","ingress-zones":"home","egress-zones":"HOST","rich rules":"rule service name=ssh accept"}}]},permanent:{zones:[{name:"home",active:false,fields:{target:"default",services:"ssh",ports:"",forward:"no",masquerade:"no"}}],policies:[]}}})
 property var definition: null
 property var definitionContext: null
 function inspect(kind,name,scope) { reads++; definitionContext={kind,name,scope}; definition={name:name,fields:{ports:"80/tcp"},revision:"detail-fixture"}; }
 property string lastValidRead: "2026-11-03T12:00:00Z"
 property string error: ""
 property string result: ""
 readonly property bool editable: !busy && snapshot.connected && snapshot.complete
 property int writes: 0
 property int reads: 0
 property var lastChange: ({})
 function apply(change) { writes++; lastChange=change; }
 function refresh() { reads++; }
}
""")
        for directory in (base / 'qs').rglob('*'):
            if not directory.is_dir(): continue
            qml = list(directory.glob('*.qml'))
            if not qml: continue
            lines = ['module ' + '.'.join(directory.relative_to(base).parts)]
            for path in qml:
                lines.append(('singleton ' if 'pragma Singleton' in path.read_text() else '') + path.stem + ' 1.0 ' + path.name)
            (directory / 'qmldir').write_text('\n'.join(lines))
        write('main.qml', """import QtQuick
import qs.modules.settings
import qs.modules.shared
import qs.modules.shared.primitives.settings
import qs.services
Rectangle {
 width:900; height:800; color:Appearance.colors.colLayer0
 property var service:FirewalldControl
 property var theme:Appearance
 property var surfaceCard:baselineCard
 SettingsCard {id:baselineCard;visible:false}
 FirewallConfig {id:page;objectName:"firewall-page"; anchors.fill:parent}
 function findControl(name) {
    function walk(item) {if(item.objectName===name)return item; for(const child of item.children || []) {const found=walk(child);if(found)return found;} return null;}
    return walk(page);
 }
 function revealControl(name) {
    const item=findControl(name);
    const scroll=findControl("firewall-scroller");
    scroll.contentY=Math.max(0,Math.min(scroll.contentHeight-scroll.height,item.mapToItem(scroll.contentItem,0,0).y-20));
 }
 function visibleCount(name) {
    function walk(item) {let count=item.visible && item.objectName===name ? 1 : 0; for(const child of item.children || []) count+=walk(child); return count;}
    return walk(page);
 }
 function checkGeometry() {
    function walk(item) {
        if(item.visible && item.objectName.startsWith("firewall-") && item!==page && item.objectName!=="firewall-scroller") {
            const p=item.mapToItem(page,0,0);
            if(p.x<19 || p.x+item.width>page.width-18)return item.objectName+":"+p.x+":"+item.width;
        }
        for(const child of item.children || []) {const error=walk(child);if(error)return error;}
        return "";
    }
    return walk(page);
 }
 function review() {page.zoneName="home"; page.review("remove-service", "ssh");}
 function resetPending() {page.pending=null;}
 function changeInventory() {
    const connections=FirewalldControl.snapshot.connections.map(c=>Object.assign({},c));
    connections[0].zone="trusted";connections[0].canAssign=false;
    FirewalldControl.snapshot=Object.assign({},FirewalldControl.snapshot,{connections});
 }
 function loseConnection(state) {FirewalldControl.snapshot={connected:false,complete:false,state:state,scopes:{},services:[],activeZones:[],differences:[]};}
 function themeMode(light) {
    let colors=Object.assign({},Appearance.colors);
    for (const key of Object.keys(colors)) colors[key]=key.startsWith("colOn") || key==="colSubtext" ? (light ? "#202124" : "#eeeeee") : (light ? "#e5e0eb" : "#39343f");
    colors.colLayer0=light ? "#faf8fc" : "#18151c";
    colors.colPrimary=light ? "#675080" : "#ddbcf5";
    colors.colOnPrimary=light ? "#ffffff" : "#35184c";
    colors.colPrimaryContainer=light ? "#eadbff" : "#49385d";
    colors.colOnPrimaryContainer=light ? "#271438" : "#edddff";
    colors.colSecondaryContainer=light ? "#dce4f0" : "#313d4d";
    colors.colOnSecondaryContainer=light ? "#162333" : "#dfebff";
    colors.colBackgroundSurfaceContainer=light ? "#d9e5e0eb" : "#c439343f";
    Appearance.colors=colors;
    Appearance.m3colors=Object.assign({},Appearance.m3colors,{darkmode:!light});
 }
}
""")
        view = QQuickView()
        view.engine().addImportPath(str(base))
        view.setSource(QUrl.fromLocalFile(str(base / 'main.qml')))
        assert view.status() == QQuickView.Ready, '\n'.join(str(error) for error in view.errors())
        view.setResizeMode(QQuickView.SizeRootObjectToView)
        view.show()
        QTest.qWait(100)
        root = view.rootObject()
        page = root.findChild(QObject, 'firewall-page')
        service = root.property('service')
        def find(name):
            return root.findControl(name)
        def click(item):
            assert item and item.isEnabled()
            if item.objectName():
                root.revealControl(item.objectName())
                QTest.qWait(10)
            point = item.mapToScene(QPointF(item.width()/2, item.height()/2))
            QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))
            QTest.qWait(30)
        assert 'Read protected configuration' not in (SOURCE / 'modules/settings/FirewallConfig.qml').read_text()
        assert service.property('active') and service.property('writes') == 0
        for light in (False, True):
            root.themeMode(light)
            for width in (360, 620, 1100):
                view.resize(width, 800)
                for tab in ('home','connections','zones','zone','section','zone-details','zone-create','resources','catalog','definition','definition-create','global','policies','diagnostics'):
                    page.setProperty('zoneName', 'home')
                    page.setProperty('section', 'rich rules')
                    page.setProperty('page', tab)
                    QTest.qWait(40)
                    assert root.checkGeometry() == "", (width, tab, root.checkGeometry())
                    assert root.visibleCount('firewall-back') == (0 if tab == 'home' else 1)
                    assert root.visibleCount('firewall-heading') == (0 if tab == 'home' else 1)
                    assert root.visibleCount('firewall-scope-selector') == (1 if tab in ('zones','catalog','policies') else 0)
                    if tab in ('zone','section','zone-details'):
                        assert page.property('scope') == 'runtime'
                        assert 'Accessible.name: "Selected zone"' not in (SOURCE / 'modules/settings/FirewallConfig.qml').read_text()
                    colors = root.property('theme').property('colors').toVariant()
                    base_color = QColor(colors['colBackgroundSurfaceContainer'])
                    assert root.property('surfaceCard').property('color') == base_color
                    for name, background, foreground in (
                        ('firewall-primary-card','colPrimaryContainer','colOnPrimaryContainer'),
                        ('firewall-status-card','colSecondaryContainer','colOnSecondaryContainer'),
                        ('firewall-zone-context','colSecondaryContainer','colOnSecondaryContainer')):
                        card = find(name)
                        expected = QColor(colors[background])
                        expected.setAlphaF(base_color.alphaF() * (0.5 if name in ('firewall-primary-card','firewall-status-card') else 1))
                        actual = card.property('color')
                        assert all(abs(a-b) < 1/255 for a,b in zip(actual.getRgbF(), expected.getRgbF())), (tab,name,actual,expected)
                        assert card.property('foregroundColor') == QColor(colors[foreground])
                    images = os.environ.get('DOTS_FIREWALL_TEST_IMAGES')
                    if images:
                        Path(images).mkdir(parents=True, exist_ok=True)
                        view.grabWindow().save(str(Path(images) / f'firewall-{width}-{tab}-{"light" if light else "dark"}.png'))
                    assert service.property('writes') == 0
        # Exercise full-row navigation with real pointer events, not only page assignments.
        view.resize(620, 800)
        page.setProperty('page', 'home')
        QTest.qWait(30)
        assert root.visibleCount('firewall-connection-info') == 1
        for destination in ('zones','connections','resources','global'):
            page.setProperty('page', 'home')
            QTest.qWait(20)
            click(find('firewall-task-' + destination))
            assert page.property('page') == destination
            assert service.property('writes') == 0
            click(find('firewall-back'))
            assert page.property('page') == 'home'
        # An inline effective-zone link retains the same one-step Back behavior.
        click(find('firewall-zone-link-fixture0'))
        assert page.property('page') == 'zone' and page.property('zoneName') == 'home'
        click(find('firewall-back'))
        assert page.property('page') == 'home' 
        page.setProperty('page', 'zones')
        QTest.qWait(20)
        click(find('firewall-zone-home'))
        assert page.property('page') == 'zone' and page.property('zoneName') == 'home'
        assert not page.property('advancedOpen')
        for field in ('services', 'ports'):
            click(find('firewall-zone-section-' + field))
            assert page.property('page') == 'section' and page.property('section') == field
            assert page.property('zoneName') == 'home'
            click(find('firewall-back'))
            assert page.property('page') == 'zone'
            assert page.property('zoneName') == 'home' and page.property('scope') == 'runtime'
            QTest.qWait(20)
        click(find('firewall-advanced-toggle'))
        assert page.property('advancedOpen')
        assert [section['title'] for section in page.property('sections').toVariant()] == [
            'Protocols','Source ports','Masquerading','Port forwarding','ICMP filter','Rich rules','Interfaces','Sources']
        click(find('firewall-zone-section-protocols'))
        assert page.property('section') == 'protocols' and page.property('zoneName') == 'home'
        # Visiting a different connection's zone must not retarget an earlier editor.
        page.setProperty('page', 'connections')
        QTest.qWait(20)
        click(find('firewall-zone-link-fixture1'))
        assert page.property('zoneName') == 'trusted'
        click(find('firewall-back'))
        assert page.property('page') == 'connections'
        click(find('firewall-back'))
        assert page.property('page') == 'section'
        assert page.property('zoneName') == 'home' and page.property('section') == 'protocols'
        page.setProperty('page', 'resources')
        QTest.qWait(20)
        click(find('firewall-catalog-service'))
        assert page.property('page') == 'catalog'
        click(find('firewall-definition-http'))
        assert page.property('page') == 'definition' and page.property('resourceName') == 'http'
        assert service.property('reads') == 1 and service.property('writes') == 0
        click(find('firewall-back'))
        assert page.property('page') == 'catalog'
        click(find('firewall-back'))
        assert page.property('page') == 'resources'
        # Scope is chosen in the zone list, then carried unchanged into every editor.
        page.setProperty('page', 'zones')
        page.setProperty('scope', 'permanent')
        QTest.qWait(20)
        click(find('firewall-zone-home'))
        click(find('firewall-zone-section-ports'))
        assert page.property('scope') == 'permanent'
        assert root.visibleCount('firewall-scope-selector') == 0
        click(find('firewall-back'))
        click(find('firewall-back'))
        assert page.property('page') == 'zones' and page.property('scope') == 'permanent'
        assert root.visibleCount('firewall-scope-selector') == 1
        page.setProperty('scope', 'runtime')
        page.setProperty('page', 'section')
        page.setProperty('section', 'ports')
        for text, valid in [('0',False),('65536',False),('100-1',False),('80',True),('1-65535',True),('80;id',False)]:
            find('firewall-port').setProperty('text', text)
            QTest.qWait(5)
            assert page.property('portValid') == valid
        view.resize(620, 1000)
        root.review()
        QTest.qWait(30)
        assert page.property('pending') is not None and service.property('writes') == 0
        click(find('firewall-cancel'))
        assert service.property('writes') == 0
        root.review()
        QTest.qWait(30)
        click(find('firewall-confirm'))
        assert service.property('writes') == 1
        assert service.property('lastChange').toVariant()['zone'] == 'home'
        # Explicit zone identity survives nested navigation and absent scopes.
        page.setProperty('zoneName', 'trusted')
        page.setProperty('page', 'section')
        page.setProperty('section', 'protocols')
        page.setProperty('scope', 'permanent')
        assert page.property('zoneName') == 'trusted'
        assert page.property('selectedZone') is None
        page.setProperty('zoneName', 'home')
        page.setProperty('scope','permanent')
        root.review()
        QTest.qWait(20)
        assert page.property('pending').toVariant()['scope'] == 'permanent'
        root.resetPending()
        # Assignment review resolves the current interface snapshot, not the
        # obsolete object captured when the user first opened the form.
        page.setProperty('assignmentInterface', 'fixture0')
        assert page.property('assignment').toVariant()['zone'] == 'home'
        root.changeInventory()
        assert page.property('assignment').toVariant()['zone'] == 'trusted'
        assert not page.property('assignment').toVariant()['canAssign']
        page.setProperty('query','does-not-exist')
        for state in ('connecting','not-installed','unavailable','access-denied','authorization-unavailable','timeout','communication-error'):
            root.loseConnection(state)
            QTest.qWait(20)
            assert not service.property('editable')
            root.review()
            assert page.property('pending') is None
            assert page.property('connectionText')
        print('FIREWALL_SETTINGS_OK: 360/620/1100, light/dark, all task views, zone context, states, validation, review/cancel/confirm')
        view.close()
        del view


if __name__ == '__main__':
    if '--offscreen' in sys.argv: offscreen()
    else: unittest.main()
