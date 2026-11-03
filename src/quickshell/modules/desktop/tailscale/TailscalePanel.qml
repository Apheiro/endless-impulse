import Quickshell
import qs.services

Scope {
    LazyLoader {
        active: TailscaleControl.opened
        component: TailscaleWindow {}
    }
}
