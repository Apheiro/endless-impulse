pragma Singleton
import QtQuick

QtObject {
    // Catalog IDs are persisted in user layouts; keep them stable.
    readonly property var sources: ({
        sidebarLeft: Qt.resolvedUrl("widgets/LeftSidebarModule.qml"),
        activeWindow: Qt.resolvedUrl("widgets/ActiveWindowModule.qml"),
        resources: Qt.resolvedUrl("widgets/ResourcesModule.qml"),
        media: Qt.resolvedUrl("widgets/MediaModule.qml"),
        workspaces: Qt.resolvedUrl("widgets/WorkspacesModule.qml"),
        clock: Qt.resolvedUrl("widgets/ClockModule.qml"),
        utilities: Qt.resolvedUrl("widgets/UtilitiesModule.qml"),
        battery: Qt.resolvedUrl("widgets/BatteryModule.qml"),
        weather: Qt.resolvedUrl("widgets/WeatherModule.qml"),
        tray: Qt.resolvedUrl("widgets/TrayModule.qml"),
        status: Qt.resolvedUrl("widgets/StatusModule.qml"),
        search: Qt.resolvedUrl("widgets/SearchModule.qml"),
        networkSpeed: Qt.resolvedUrl("widgets/NetworkSpeedModule.qml"),
        updates: Qt.resolvedUrl("widgets/UpdatesModule.qml"),
        power: Qt.resolvedUrl("widgets/PowerModule.qml"),
        profile: Qt.resolvedUrl("widgets/ProfileModule.qml"),
        keyboard: Qt.resolvedUrl("widgets/KeyboardModule.qml"),
        recording: Qt.resolvedUrl("widgets/RecordingModule.qml"),
        separator: Qt.resolvedUrl("widgets/SeparatorModule.qml"),
        spacer: Qt.resolvedUrl("widgets/FixedSpaceModule.qml"),
        flex: Qt.resolvedUrl("widgets/FlexibleSpaceModule.qml")
    })
    function sourceFor(type) { return sources[type] ?? ""; }
}
