import QtQuick
import Quickshell

import qs.modules.shared

LazyLoader {
    property bool extraCondition: true
    active: Config.ready && extraCondition
}
