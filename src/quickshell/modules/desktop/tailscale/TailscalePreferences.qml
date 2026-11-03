pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.widgets
GridLayout {
    id: root
    columns: width >= 720 ? 2 : 1
    columnSpacing: 12; rowSpacing: 12
    TailscaleCard {
        Layout.alignment: Qt.AlignTop
        title: Translation.tr("Network & DNS"); subtitle: Translation.tr("How this device uses your tailnet"); icon: "hub"
        TailscalePreference { preferenceKey: "accept-dns"; label: Translation.tr("Use Tailscale DNS"); description: Translation.tr("Resolve tailnet names with MagicDNS"); icon: "dns" }
        TailscalePreference { preferenceKey: "accept-routes"; label: Translation.tr("Accept subnet routes"); description: Translation.tr("Reach networks shared by other devices"); icon: "route" }
        TailscalePreference { preferenceKey: "hostname"; label: Translation.tr("Device name"); icon: "computer" }
    }
    TailscaleCard {
        Layout.alignment: Qt.AlignTop
        title: Translation.tr("Security & access"); subtitle: Translation.tr("Control incoming connections and remote access"); icon: "shield"
        TailscalePreference { preferenceKey: "shields-up"; label: Translation.tr("Block incoming connections"); description: Translation.tr("Allow outgoing traffic only"); icon: "gpp_good" }
        TailscalePreference { preferenceKey: "ssh"; label: Translation.tr("Tailscale SSH"); description: Translation.tr("Use the access rules defined in your tailnet"); icon: "terminal" }
        TailscalePreference { preferenceKey: "webclient"; label: Translation.tr("Device web interface"); description: Translation.tr("Manage this device over Tailscale on port 5252"); icon: "web" }
    }
    TailscaleCard {
        Layout.columnSpan: root.columns
        title: Translation.tr("Subnet routing"); subtitle: Translation.tr("Share local networks with your tailnet; use comma-separated CIDR ranges"); icon: "router"
        TailscalePreference { preferenceKey: "advertise-routes"; label: Translation.tr("Advertised networks"); icon: "lan" }
    }
}
