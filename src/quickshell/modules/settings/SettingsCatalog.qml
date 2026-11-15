import QtQuick
import qs.services

QtObject {
    // Keep navigation, descriptions and search terms together. Config keys stay unchanged.
    readonly property var pages: [
        { group: Translation.tr("Appearance"), name: Translation.tr("Wallpaper & colors"), icon: "palette", component: "ThemeConfig.qml",
          description: Translation.tr("Wallpaper, color scheme, transparency, animation speed, Xray and application themes."),
          keywords: "theme dark light wallpaper color transparency parallax terminal qt fondo colores tema transparencia esquinas xray blur desenfoque animation speed animations animaciones velocidad" },
        { group: Translation.tr("Appearance"), name: Translation.tr("Icons"), icon: "interests", component: "IconsConfig.qml",
          description: Translation.tr("System icon themes, application overrides and environment configuration files."), keywords: "icons theme gtk qt kde applications overrides environment paths iconos tema aplicaciones entornos rutas" },
        { group: Translation.tr("Appearance"), name: Translation.tr("Typography"), icon: "text_fields", component: "FontsConfig.qml",
          description: Translation.tr("Fonts for the interface, clocks, reading and icons."), keywords: "font text numbers monospace nerd fuente tipografia letras" },
        { group: Translation.tr("Appearance"), name: Translation.tr("Bar & tray"), icon: "toolbar", component: "BarConfig.qml",
          description: Translation.tr("Position, workspace indicators, tray icons and utility buttons."), keywords: "bar tray icons workspace weather tooltip barra bandeja iconos espacios" },
        { group: Translation.tr("Desktop"), name: Translation.tr("Desktop widgets"), icon: "widgets", component: "WidgetsConfig.qml",
          description: Translation.tr("Desktop clock styles, date, quotes and weather widgets."), keywords: "clock weather date quote digital analog reloj clima fecha widgets" },
        { group: Translation.tr("Desktop"), name: Translation.tr("Panels & notifications"), icon: "dock_to_right", component: "PanelsConfig.qml",
          description: Translation.tr("Dock, sidebars, quick controls, notification popups and volume indicators."), keywords: "dock sidebar notification osd brightness volume translator panels paneles notificaciones brillo volumen" },
        { group: Translation.tr("Desktop"), name: Translation.tr("Overview & search"), icon: "overview", component: "OverviewConfig.qml",
          description: Translation.tr("Workspace previews, overview layout and launcher search behavior."), keywords: "super windows preview rows columns launcher search prefix web ventanas workspaces buscar busqueda lanzador" },
        { group: Translation.tr("Desktop"), name: Translation.tr("Shortcuts"), icon: "keyboard", component: "ShortcutsConfig.qml",
          description: Translation.tr("Edit keyboard and mouse shortcuts and customize the shortcut guide."), keywords: "shortcut keybind keyboard mouse cheat sheet atajos teclado raton teclas" },
        { group: Translation.tr("System"), name: Translation.tr("Hardware"), icon: "developer_board", component: "HardwareConfig.qml",
          description: Translation.tr("Physical hardware tree, interfaces, kernel drivers, permissions and own udev rule drafts."), keywords: "hardware device manager usb pci hid hidraw cpu gpu nvme storage driver kernel firmware udev permissions dispositivos administrador controladores permisos arbol" },
        { group: Translation.tr("System"), name: Translation.tr("Storage"), icon: "hard_drive", component: "StorageConfig.qml",
          description: Translation.tr("Volume capacity, available space and on-demand folder usage analysis."), keywords: "storage disk filesystem volume space folders usage almacenamiento disco espacio carpetas uso volumen" },
        { group: Translation.tr("System"), name: Translation.tr("Monitors"), icon: "monitor", component: "MonitorsConfig.qml",
          description: Translation.tr("Arrange displays and choose resolution, refresh rate, scale and orientation."), keywords: "monitor display resolution refresh scale orientation pantalla monitores resolucion frecuencia escala orientacion" },
        { group: Translation.tr("System"), name: Translation.tr("Windows & effects"), icon: "select_window", component: "HyprlandConfig.qml",
          description: Translation.tr("Tiling, borders, gaps, opacity, blur, shadows and animations."), keywords: "hyprland windows gaps border rounding blur shadow opacity animation ventanas bordes espacios efectos desenfoque sombras" },
        { group: Translation.tr("System"), name: Translation.tr("Internal graphical processes"), icon: "account_tree", component: "InternalSurfacesConfig.qml",
          description: Translation.tr("Reserved workspace for auxiliary surfaces, legacy tray bridge and exact window rules."), keywords: "internal graphical processes xembed tray surfaces workspace procesos graficos internos superficies auxiliares bandeja reglas ventanas" },
        { group: Translation.tr("System"), name: Translation.tr("Keyboard & mouse"), icon: "keyboard_alt", component: "InputConfig.qml",
          description: Translation.tr("Keyboard layouts, repeat rate, pointer behavior, touchpad and individual devices."), keywords: "input keyboard mouse touchpad layout repeat sensitivity device teclado raton distribucion repeticion sensibilidad dispositivos" },
        { group: Translation.tr("System"), name: Translation.tr("Sound"), icon: "volume_up", component: "AudioConfig.qml", description: Translation.tr("Applications, devices, profiles and advanced PipeWire routing."), keywords: "audio sound pipewire volume applications sonido volumen dispositivos" },
        { group: Translation.tr("System"), name: Translation.tr("Network"), icon: "lan", component: "NetworkConfig.qml", description: Translation.tr("Wi-Fi, Ethernet, saved connections, IP addresses, DNS and routes."), keywords: "wifi ethernet network vpn internet red redes conexiones dns" },
        { group: Translation.tr("System"), name: Translation.tr("Firewall"), icon: "shield", component: "FirewallConfig.qml",
          description: Translation.tr("Security & Network Control: Firewalld connection, zones, services, ports and policies."), keywords: "firewall firewalld security network zones ports services policies cortafuegos seguridad red zonas puertos servicios politicas" },
        { group: Translation.tr("System"), name: Translation.tr("Bluetooth"), icon: "bluetooth", component: "BluetoothConfig.qml", description: Translation.tr("Pairing, connected devices, adapters and device permissions."), keywords: "bluetooth devices pairing wireless dispositivos emparejar" },
        { group: Translation.tr("System"), name: Translation.tr("Sound & power"), icon: "battery_charging_full", component: "SystemConfig.qml",
          description: Translation.tr("Volume protection, battery warnings, sounds and resource monitoring."), keywords: "audio battery suspend resources polling sound power energia bateria sonido volumen recursos" },
        { group: Translation.tr("System"), name: Translation.tr("Language & time"), icon: "language", component: "LocaleConfig.qml",
          description: Translation.tr("Interface language, translations and clock format."), keywords: "locale translation time clock language idioma traduccion hora formato segundos" },
        { group: Translation.tr("System"), name: Translation.tr("Lock & privacy"), icon: "lock", component: "SecurityConfig.qml",
          description: Translation.tr("Lock screen, authentication, content policies and clipboard privacy."), keywords: "lock password keyring privacy ai policy safety security bloqueo clave privacidad seguridad" },
        { group: Translation.tr("Tools & services"), name: Translation.tr("Recording"), icon: "videocam", component: "RecordingConfig.qml",
          description: Translation.tr("GPU Screen Recorder, video quality, audio tracks, filenames, replay and streaming."), keywords: "recording video gpu screen recorder fps format date paths audio replay stream grabacion video grabar fecha hora rutas" },
        { group: Translation.tr("Tools & services"), name: Translation.tr("Capture & overlays"), icon: "screenshot_region", component: "CaptureConfig.qml",
          description: Translation.tr("Screen capture, region selection, crosshair, floating images and save locations."), keywords: "screenshot record capture overlay crosshair lens image path captura grabacion imagen rutas" },
        { group: Translation.tr("Tools & services"), name: Translation.tr("Online services"), icon: "cloud", component: "ServicesConfig.qml",
          description: Translation.tr("Weather location, music recognition, AI instructions and network requests."), keywords: "weather gps fahrenheit music recognition ai prompt network clima musica inteligencia red ubicacion" },
        { group: Translation.tr("Tools & services"), name: Translation.tr("About"), icon: "info", component: "About.qml",
          description: Translation.tr("Project details, system information and interactive installation paths and a transparent dependency map."), keywords: "about version distro help credits paths folders files tree map cache state acerca version sistema ayuda rutas carpetas archivos arbol mapa dependencies packages dependencias paquetes servicios" }
    ]

    function normalize(text) {
        return text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    }

    function matches(index, query) {
        const page = pages[index];
        const terms = normalize(query).trim().split(/\s+/);
        const haystack = normalize(`${page.group} ${page.name} ${page.description} ${page.keywords}`);
        return terms.every(term => haystack.includes(term));
    }
}
