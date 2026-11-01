import qs.services
import qs.modules.desktop.quickPanels

StatusPanelButton {
    section: "audio"
    materialIcon: Audio.sink?.audio?.muted ? "volume_off" : "volume_up"
    glyphName: "audio-button-glyph"
}
