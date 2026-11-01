pragma ComponentBehavior: Bound
import QtQuick
import qs.modules.shared

Item {
    id: root
    required property Item source
    property color tintColor: Appearance.colors.colPrimary

    ShaderEffectSource {
        id: texture
        sourceItem: root.source
        visible: false
        live: true
    }
    ShaderEffect {
        anchors.fill: parent
        property var source: texture
        property color tintColor: root.tintColor
        fragmentShader: Qt.resolvedUrl("../../widgets/shaders/color-tint.frag.qsb")
    }
}
