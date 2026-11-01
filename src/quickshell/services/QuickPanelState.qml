pragma Singleton
import Quickshell
import qs

Singleton {
    id: root
    property string section: ""
    readonly property var controller: section === "audio" ? AudioControl : section === "network" ? NetworkControl : section === "bluetooth" ? BluetoothManager : null
    function activate(next) {
        // Claim the surface before closing the previous service: switching must
        // never produce an empty section and unmap the shared window.
        section = next;
        if (next !== "audio" && AudioControl.opened) AudioControl.close();
        if (next !== "network" && NetworkControl.opened) NetworkControl.close();
        if (next !== "bluetooth" && BluetoothManager.opened) BluetoothManager.close();
    }
    function deactivate(previous) { if (section === previous) section = ""; }
    function toggleSidebar() {
        // Add the sidebar to the shared focus grab before releasing the popup.
        GlobalStates.sidebarRightOpen = !GlobalStates.sidebarRightOpen;
        dismiss();
    }
    function dismiss() {
        const active = controller;
        section = "";
        if (active) active.close();
    }
}
