pragma ComponentBehavior: Bound
import QtQuick
import qs
import qs.services
import qs.modules.shared
import qs.modules.shared.primitives.common
import qs.modules.shared.primitives.bar
import qs.modules.desktop.bar

import qs.modules.desktop.bar.weather
BarModuleBase {
    id: root
    available: Config.options.bar.independentLayouts || Config.options.bar.weather.enable
    Loader {
        anchors.fill: parent
        active: root.available
        sourceComponent: WeatherBar {}
    }
}
