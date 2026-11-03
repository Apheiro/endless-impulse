import qs.services
import qs.modules.shared

QuickToggleModel {
    name: "Tailscale"
    statusText: TailscaleControl.state.running ? TailscaleControl.state.tailnet : Translation.tr("Disconnected")
    tooltipText: Translation.tr("Left-click to connect or disconnect; right-click to configure")
    icon: "vpn_lock"
    available: true
    toggled: TailscaleControl.state.running
    mainAction: () => TailscaleControl.toggle()
    hasMenu: true
    altAction: () => TailscaleControl.open()
}
