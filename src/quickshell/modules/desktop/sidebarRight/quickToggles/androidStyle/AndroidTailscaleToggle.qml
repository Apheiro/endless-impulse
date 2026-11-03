import qs.services
import qs.modules.shared.models.quickToggles

AndroidQuickToggleButton {
    toggleModel: TailscaleToggle {}
    iconSource: "tailscale-symbolic.svg"
    clickOpensMenu: false
    onOpenMenu: TailscaleControl.open()
}
