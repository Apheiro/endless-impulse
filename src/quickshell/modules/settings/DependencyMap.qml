pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import "../shared/functions/PathTree.js" as PathTree

ColumnLayout {
    id: root
    property string query: ""
    property var expanded: ({})
    property string selected: ""
    property bool showSources: false
    readonly property var rows: PathTree.flatten(DependencyInfo.groups, expanded, query)
    Layout.fillWidth: true
    spacing: 8
    function toggle(id) { const next = Object.assign({}, expanded); next[id] = !next[id]; expanded = next; }
    Component.onCompleted: DependencyInfo.refresh()
    StyledText {
        Layout.fillWidth: true
        text: DependencyInfo.busy ? Translation.tr("Reading dependency manifests…") : DependencyInfo.error || DependencyInfo.catalog.total + " " + Translation.tr("declared packages") + " · " + (DependencyInfo.catalog.reference || "Arch Linux")
        wrapMode: Text.WordWrap
        font.pixelSize: Appearance.font.pixelSize.small
        color: DependencyInfo.error ? Appearance.m3colors.m3error : Appearance.colors.colPrimary
    }
    StyledText {
        Layout.fillWidth: true
        text: Translation.tr("Project requirements, not an inventory of this computer. Package names follow the Arch installer; Fedora and Nix use their own manifests and runtimes.")
        wrapMode: Text.WordWrap
        font.pixelSize: Appearance.font.pixelSize.smaller
        color: Appearance.colors.colSubtext
    }
    RowLayout {
        Layout.fillWidth: true
        MaterialTextField { Layout.fillWidth: true; wrapMode: TextInput.NoWrap; placeholderText: Translation.tr("Find a package, feature or service…"); onTextChanged: root.query = text }
        RippleButtonWithIcon { materialIcon: "refresh"; mainText: ""; Accessible.name: Translation.tr("Refresh dependency map"); enabled: !DependencyInfo.busy; onClicked: DependencyInfo.refresh() }
        RippleButtonWithIcon { materialIcon: "unfold_less"; mainText: ""; Accessible.name: Translation.tr("Collapse dependency branches"); onClicked: { root.expanded = {}; root.selected = ""; } }
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 2
        Repeater {
            model: root.rows
            delegate: Item {
                id: treeRow
                required property var modelData
                readonly property var node: modelData.node
                readonly property bool branch: node.children.length > 0
                readonly property bool detailed: root.selected === node.id
                Layout.fillWidth: true
                implicitHeight: button.implicitHeight
                Rectangle { visible: treeRow.modelData.depth > 0; x: 10; width: 1; height: parent.height; color: Appearance.colors.colLayer0Border }
                Rectangle { visible: treeRow.modelData.depth > 0; x: 10; y: parent.height / 2; width: 14; height: 1; color: Appearance.colors.colLayer0Border }
                RippleButton {
                    id: button
                    anchors { left: parent.left; right: parent.right; leftMargin: treeRow.modelData.depth * 24 }
                    implicitHeight: body.implicitHeight + 14
                    horizontalPadding: 8
                    onClicked: { if (treeRow.branch) root.toggle(treeRow.node.id); else root.selected = treeRow.detailed ? "" : treeRow.node.id; }
                    altAction: () => { if (treeRow.node.package) Quickshell.clipboardText = treeRow.node.package; }
                    contentItem: RowLayout {
                        spacing: 8
                        MaterialSymbol { text: treeRow.branch ? (treeRow.modelData.expanded ? "expand_more" : "chevron_right") : treeRow.node.optional ? "extension" : "deployed_code"; iconSize: 19; color: treeRow.branch ? Appearance.colors.colPrimary : Appearance.colors.colSubtext }
                        ColumnLayout {
                            id: body
                            Layout.fillWidth: true
                            spacing: 3
                            RowLayout {
                                Layout.fillWidth: true
                                StyledText { Layout.fillWidth: true; text: treeRow.branch ? Translation.tr(treeRow.node.title) : treeRow.node.title; textFormat: Text.PlainText; elide: Text.ElideRight; font.weight: treeRow.branch ? Font.Medium : Font.Normal; font.pixelSize: Appearance.font.pixelSize.small }
                                StyledText { text: treeRow.branch ? String(treeRow.node.count) : treeRow.node.origin || ""; color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
                            }
                            StyledText { Layout.fillWidth: true; visible: treeRow.branch || treeRow.detailed; text: Translation.tr(treeRow.node.description); textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
                            StyledText { visible: !treeRow.branch; text: Translation.tr(treeRow.node.scope || ""); font.pixelSize: Appearance.font.pixelSize.smaller; color: Appearance.colors.colSubtext }
                        }
                    }
                }
            }
        }
    }
    StyledText { visible: !DependencyInfo.busy && !root.rows.length; text: Translation.tr("No matching dependencies"); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.small }
    RippleButtonWithIcon { materialIcon: root.showSources ? "expand_less" : "data_object"; mainText: Translation.tr("Sources & lockfiles"); onClicked: root.showSources = !root.showSources }
    ColumnLayout {
        visible: root.showSources
        Layout.fillWidth: true
        StyledText { Layout.fillWidth: true; text: Translation.tr("Nix pins the application runtime; host services remain provided by the operating system. Python and MathJax also have explicit dependency definitions."); wrapMode: Text.WordWrap; font.pixelSize: Appearance.font.pixelSize.smaller; color: Appearance.colors.colSubtext }
        Repeater {
            model: DependencyInfo.catalog.sources || []
            delegate: RippleButtonWithIcon {
                required property var modelData
                Layout.fillWidth: true
                materialIcon: "description"
                mainText: modelData.name
                onClicked: Qt.openUrlExternally("file://" + encodeURI(modelData.path).replace(/#/g, "%23").replace(/\?/g, "%3F"))
            }
        }
        StyledText { Layout.fillWidth: true; text: (DependencyInfo.catalog.liveManifest ? Translation.tr("Read from this checkout") : Translation.tr("Bundled build snapshot")) + " · " + (DependencyInfo.catalog.fingerprint || "").slice(0, 12); wrapMode: Text.WordWrap; font.pixelSize: Appearance.font.pixelSize.smaller; color: Appearance.colors.colSubtext }
    }
}
