import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common

QuickToggleButton {
    id: root
    buttonIcon: "vpn_lock"
    iconSource: "tailscale-symbolic.svg"
    toggled: TailscaleControl.state.running
    onClicked: TailscaleControl.toggle()
    altAction: () => TailscaleControl.open()
    StyledToolTip { text: "Tailscale"; extraVisibleCondition: root.hovered }
}
