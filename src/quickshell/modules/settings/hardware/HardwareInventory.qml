pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.settings
import qs.modules.shared.widgets

ColumnLayout {
    id: root
    property string mode: "categories"
    property string category: ""
    property string query: ""
    property var expanded: ({})
    property int budget: 60
    property bool advanced: false
    property int offset: 0
    property var pageHistory: []
    readonly property bool overview: mode === "categories" && category === "" && query.trim() === ""
    readonly property var result: overview ? ({rows: [], total: 0, more: false}) : Hardware.browse(mode, query, category, expanded, budget, offset)
    signal chosen(string identity)
    Layout.minimumWidth: 0
    spacing: 10
    function resetPage() { budget = 60; offset = 0; pageHistory = []; }
    onModeChanged: { resetPage(); expanded = ({}); category = ""; }
    onCategoryChanged: resetPage()
    onQueryChanged: resetPage()
    function toggle(identity) {
        const next = Object.assign({}, expanded);
        next[identity] = !next[identity];
        expanded = next;
    }
    function reveal(identity) {
        mode = "topology";
        category = "";
        search.text = "";
        expanded = Hardware.reveal(identity);
    }
    MaterialTextField {
        id: search
        objectName: "hardware-search"
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        placeholderText: Translation.tr("Find a component or interface")
        Accessible.name: placeholderText
        wrapMode: TextInput.NoWrap
        onTextChanged: root.query = text
    }
    SegmentedControl {
        objectName: "hardware-browse-mode"
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        currentIndex: root.mode === "categories" ? 0 : root.mode === "topology" ? 1 : -1
        model: [{name: Translation.tr("Categories"), icon: "category"}, {name: Translation.tr("Connections"), icon: "account_tree"}]
        onActivated: index => { root.mode = index === 0 ? "categories" : "topology"; root.advanced = false; }
    }
    RowLayout {
        visible: !root.overview
        Layout.fillWidth: true
        RippleButtonWithIcon {
            objectName: "hardware-category-back"
            materialIcon: "arrow_back"
            mainText: Translation.tr("Categories")
            onClicked: { root.mode = "categories"; root.category = ""; search.text = ""; root.advanced = false; }
        }
        HardwareText {
            text: root.mode === "technical" ? Translation.tr("Technical nodes (sysfs)") : root.category ? Translation.tr(Hardware.projection.categories.find(c => c.id === root.category)?.name || root.category) : Translation.tr("Connections")
        }
    }
    HardwareText {
        visible: !root.overview
        color: Appearance.colors.colSubtext
        text: root.query.trim() ? Translation.tr("Matching results") + ": " + root.result.total
            : root.mode === "categories" ? Translation.tr("Components") + ": " + root.result.total
            : Translation.tr("Branches start collapsed. Expand only the connection you need.")
    }
    // Exactly one inventory viewport is visible: compact category tiles or results.
    GridView {
        id: overviewGrid
        objectName: "hardware-category-grid"
        visible: root.overview
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 0
        clip: true
        cellWidth: width / (width >= 270 ? 2 : 1)
        cellHeight: Appearance.font.pixelSize.small * 7
        model: visible ? Hardware.projection.categories : []
        ScrollBar.vertical: StyledScrollBar {}
        delegate: RippleButton {
            id: tile
            required property var modelData
            required property int index
            objectName: "hardware-row-" + index
            width: overviewGrid.cellWidth - 6
            height: overviewGrid.cellHeight - 6
            colBackground: Appearance.colors.colLayer1
            Accessible.name: Translation.tr(modelData.name) + ": " + modelData.count
            onClicked: root.category = modelData.id
            contentItem: ColumnLayout {
                spacing: 4
                RowLayout {
                    Layout.fillWidth: true
                    MaterialSymbol { text: tile.modelData.icon; iconSize: 22; color: Appearance.colors.colPrimary }
                    Item { Layout.fillWidth: true }
                    HardwareText { Layout.fillWidth: false; text: String(tile.modelData.count); color: Appearance.colors.colPrimary; font.weight: Font.DemiBold }
                }
                HardwareText { text: Translation.tr(tile.modelData.name); maximumLineCount: 2; elide: Text.ElideRight; font.weight: Font.Medium }
                HardwareText { visible: tile.modelData.secondary; text: Translation.tr("Available on demand"); color: Appearance.colors.colSubtext; font.pixelSize: Appearance.font.pixelSize.smaller }
            }
        }
    }
    StyledListView {
        id: list
        objectName: "hardware-inventory-list"
        visible: !root.overview
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 0
        animateAppearance: false
        clip: true
        spacing: 6
        model: root.overview ? [] : root.result.rows
        onModelChanged: positionViewAtBeginning()
        delegate: RippleButton {
            id: row
            required property var modelData
            required property int index
            objectName: "hardware-row-" + index
            width: list.width
            implicitHeight: content.implicitHeight + 20
            horizontalPadding: 10
            colBackground: root.overview ? Appearance.colors.colLayer1 : "transparent"
            toggled: !root.overview && (Hardware.selectedId === modelData.id || Hardware.selectedEntity?.id === modelData.id)
            Accessible.name: root.overview ? Translation.tr(modelData.name) + ": " + modelData.count : modelData.name
            onClicked: {
                if (root.overview) root.category = modelData.id;
                else root.chosen(modelData.id);
            }
            Keys.onRightPressed: { if (!root.overview && modelData.hasChildren && !root.expanded[modelData.id]) root.toggle(modelData.id); }
            Keys.onLeftPressed: { if (!root.overview && root.expanded[modelData.id]) root.toggle(modelData.id); }
            contentItem: RowLayout {
                id: content
                spacing: 8
                Item { visible: !root.overview; Layout.preferredWidth: Math.min(row.modelData.depth || 0, 6) * 10 }
                RippleButtonWithIcon {
                    visible: !root.overview && root.mode !== "categories" && !root.query.trim()
                    objectName: "hardware-branch-" + row.index
                    enabled: !!row.modelData.hasChildren
                    materialIcon: root.expanded[row.modelData.id] ? "expand_more" : "chevron_right"
                    mainText: ""
                    surfaceVisible: false
                    Accessible.name: Translation.tr("Expand this branch") + ": " + row.modelData.name
                    onClicked: root.toggle(row.modelData.id)
                }
                MaterialSymbol {
                    visible: root.overview
                    text: row.modelData.icon || "developer_board"
                    iconSize: 22
                    color: row.toggled ? Appearance.m3colors.m3onPrimary : Appearance.colors.colPrimary
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 3
                    HardwareText {
                        text: root.overview ? Translation.tr(row.modelData.name) : row.modelData.name
                        color: row.toggled ? Appearance.m3colors.m3onPrimary : Appearance.colors.colOnLayer0
                        font.weight: Font.Medium
                    }
                    HardwareText {
                        font.pixelSize: Appearance.font.pixelSize.smaller
                        color: row.toggled ? Appearance.m3colors.m3onPrimary : Appearance.colors.colSubtext
                        maximumLineCount: 2
                        elide: Text.ElideMiddle
                        text: root.overview ? (row.modelData.secondary ? Translation.tr("Available on demand") : Translation.tr("Components"))
                            : root.query.trim() ? row.modelData.breadcrumb : (row.modelData.summary || row.modelData.subsystem || "") + (row.modelData.interfaceCount ? " · " + row.modelData.interfaceCount + " " + Translation.tr("interfaces") : "")
                    }
                }
                HardwareText {
                    visible: root.overview
                    Layout.fillWidth: false
                    text: String(row.modelData.count || 0)
                    color: Appearance.colors.colPrimary
                    font.pixelSize: Appearance.font.pixelSize.larger
                }
            }
        }
        footer: ColumnLayout {
            width: list.width
            spacing: 8
            HardwareText {
                visible: !root.overview && root.result.total === 0
                text: Hardware.busy ? Translation.tr("Reading…") : Translation.tr("No matching components. Try another name, ID or category.")
            }
            RippleButtonWithIcon {
                objectName: "hardware-show-more"
                Layout.fillWidth: true
                visible: !root.overview && root.result.more && root.budget < 600
                mainText: Translation.tr("Show more") + " · " + root.result.rows.length + " / " + root.result.total
                materialIcon: "expand_more"
                onClicked: root.budget += 60
            }
            RippleButtonWithIcon {
                visible: !root.overview && root.result.more && root.budget >= 600
                mainText: Translation.tr("Next results")
                materialIcon: "chevron_right"
                onClicked: { root.pageHistory = root.pageHistory.concat([root.offset]); root.offset += root.budget; root.budget = 60; }
            }
            RippleButtonWithIcon {
                visible: !root.overview && root.offset > 0
                mainText: Translation.tr("Previous results")
                materialIcon: "chevron_left"
                onClicked: { const history = root.pageHistory.slice(); root.offset = history.pop() || 0; root.pageHistory = history; root.budget = 600; }
            }
            HardwareText {
                visible: !root.overview && root.result.more && root.budget >= 600
                text: Translation.tr("Continue to the next page or refine your search. Up to 600 rows per page.")
            }
        }
    }
    RippleButtonWithIcon {
        objectName: "hardware-advanced-mode"
        Layout.fillWidth: true
        materialIcon: "code"
        mainText: Translation.tr("Advanced: technical nodes (sysfs)")
        toggled: root.mode === "technical"
        onClicked: { root.mode = "technical"; root.advanced = true; search.text = ""; }
    }
}
