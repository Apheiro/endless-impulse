pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets
import qs.modules.shared.functions
import "../shared/functions/PathTree.js" as PathTree

ColumnLayout {
    id: root
    Layout.fillWidth: true
    spacing: 8
    property string query: ""
    property var expanded: ({"group:configuration": true})
    readonly property var rows: PathTree.flatten(InstallationPaths.groups, expanded, query)
    readonly property int pathCount: PathTree.count(InstallationPaths.groups)

    function toggle(id) {
        const next = Object.assign({}, expanded);
        next[id] = !next[id];
        expanded = next;
    }
    function openNode(node) {
        if (node.path && node.exists) Qt.openUrlExternally("file://" + encodeURI(node.path).replace(/#/g, "%23").replace(/\?/g, "%3F"));
    }
    Component.onCompleted: InstallationPaths.refresh()

    RowLayout {
        Layout.fillWidth: true
        MaterialTextField {
            Layout.fillWidth: true
            placeholderText: Translation.tr("Find a folder, feature or environment…")
            onTextChanged: root.query = text
        }
        RippleButton {
            implicitWidth: 32
            implicitHeight: 32
            enabled: !InstallationPaths.busy
            onClicked: InstallationPaths.refresh()
            contentItem: MaterialSymbol { text: "refresh"; iconSize: 18 }
            StyledToolTip { text: Translation.tr("Refresh paths") }
        }
        RippleButton {
            implicitWidth: 32
            implicitHeight: 32
            onClicked: { root.expanded = {}; }
            contentItem: MaterialSymbol { text: "unfold_less"; iconSize: 18 }
            StyledToolTip { text: Translation.tr("Collapse branches") }
        }
    }
    StyledText {
        Layout.fillWidth: true
        text: InstallationPaths.error || (InstallationPaths.busy ? Translation.tr("Reading installation paths…") : root.pathCount + " " + Translation.tr("locations") + " · " + Translation.tr("Endless Impulse"))
        color: InstallationPaths.error ? Appearance.m3colors.m3error : Appearance.colors.colSubtext
        font.pixelSize: Appearance.font.pixelSize.smaller
        wrapMode: Text.WordWrap
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 0
        Repeater {
            model: root.rows
            delegate: Item {
                id: treeRow
                required property var modelData
                readonly property var node: modelData.node
                readonly property bool hasChildren: node.children.length > 0
                readonly property int indentation: 16
                readonly property int stem: modelData.depth * indentation + 8
                Layout.fillWidth: true
                implicitHeight: row.implicitHeight + 10

                Repeater {
                    model: treeRow.modelData.lines
                    delegate: Rectangle {
                        required property bool modelData
                        required property int index
                        visible: modelData && index > 0
                        x: index * treeRow.indentation + 8
                        width: 1
                        height: treeRow.height
                        color: Appearance.colors.colOutlineVariant
                        opacity: 0.5
                    }
                }
                Rectangle {
                    visible: treeRow.modelData.depth > 0
                    x: treeRow.stem - treeRow.indentation
                    width: 1
                    height: treeRow.modelData.last ? treeRow.height / 2 : treeRow.height
                    color: Appearance.colors.colOutlineVariant
                    opacity: 0.5
                }
                Rectangle {
                    visible: treeRow.modelData.depth > 0
                    x: treeRow.stem - treeRow.indentation
                    y: treeRow.height / 2
                    width: treeRow.indentation
                    height: 1
                    color: Appearance.colors.colOutlineVariant
                    opacity: 0.5
                }
                RowLayout {
                    id: row
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: treeRow.stem }
                    spacing: 4
                    RippleButton {
                        Layout.preferredWidth: 24
                        Layout.preferredHeight: 30
                        enabled: treeRow.hasChildren
                        opacity: treeRow.hasChildren ? 1 : 0
                        onClicked: root.toggle(treeRow.node.id)
                        contentItem: MaterialSymbol {
                            text: treeRow.modelData.expanded ? "expand_more" : "chevron_right"
                            iconSize: 18
                        }
                    }
                    RippleButton {
                        id: location
                        Layout.fillWidth: true
                        implicitHeight: contentItem.implicitHeight + 8
                        opacity: !treeRow.node.path || treeRow.node.exists ? 1 : 0.42
                        pointingHandCursor: !treeRow.node.path || treeRow.node.exists
                        onClicked: {
                            if (!treeRow.node.path) root.toggle(treeRow.node.id);
                            else root.openNode(treeRow.node);
                        }
                        altAction: () => { if (treeRow.node.path) Quickshell.clipboardText = treeRow.node.path; }
                        contentItem: RowLayout {
                            spacing: 10
                            MaterialSymbol {
                                text: treeRow.node.icon
                                iconSize: 19
                                color: treeRow.node.path ? Appearance.colors.colSubtext : Appearance.colors.colPrimary
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                RowLayout {
                                    Layout.fillWidth: true
                                    StyledText {
                                        Layout.fillWidth: true
                                        text: treeRow.node.title
                                        elide: Text.ElideMiddle
                                        font.weight: treeRow.node.path ? Font.Normal : Font.Medium
                                        font.pixelSize: Appearance.font.pixelSize.small
                                    }
                                    StyledText {
                                        visible: !treeRow.node.path
                                        text: PathTree.count(treeRow.node.children)
                                        font.pixelSize: Appearance.font.pixelSize.smaller
                                        color: Appearance.colors.colSubtext
                                    }
                                }
                                StyledText {
                                    visible: !!treeRow.node.path
                                    Layout.fillWidth: true
                                    text: treeRow.node.description || ""
                                    wrapMode: Text.WordWrap
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                    font.pixelSize: Appearance.font.pixelSize.smaller
                                    color: Appearance.colors.colSubtext
                                }
                                StyledText {
                                    visible: treeRow.node.tags.length > 1
                                    Layout.fillWidth: true
                                    text: treeRow.node.tags.join(" · ")
                                    elide: Text.ElideRight
                                    font.pixelSize: Appearance.font.pixelSize.smaller
                                    color: Appearance.colors.colPrimary
                                    opacity: 0.75
                                }
                            }
                        }
                        StyledToolTip {
                            text: [treeRow.node.path, treeRow.node.target && treeRow.node.target !== treeRow.node.path ? "→ " + treeRow.node.target : "",
                                ...(treeRow.node.uses || []), treeRow.node.path && !treeRow.node.exists ? Translation.tr("Not created yet") : ""].filter(Boolean).join("\n")
                        }
                    }
                    RippleButton {
                        implicitWidth: 28
                        implicitHeight: 28
                        visible: !!treeRow.node.path
                        opacity: hovered || location.hovered ? 1 : 0.25
                        onClicked: Quickshell.clipboardText = treeRow.node.path
                        contentItem: MaterialSymbol { text: "content_copy"; iconSize: 14 }
                        StyledToolTip { text: Translation.tr("Copy path") }
                    }
                }
            }
        }
    }
    StyledText {
        Layout.fillWidth: true
        visible: InstallationPaths.loaded && root.rows.length === 0
        text: Translation.tr("No matching locations")
        color: Appearance.colors.colSubtext
        font.pixelSize: Appearance.font.pixelSize.small
    }
}
