# Shared UI surfaces

Import `QtQuick`, `qs.modules.shared.primitives.common` and `qs.modules.shared`.
Also import `QtQuick.Layouts` for examples that use layouts.
`PanelSurface` is the background for a panel, window or popup. It is a
`Rectangle`, so existing children, parents, anchors, Layout attached properties,
transforms, clipping and keyboard handlers retain native Qt Quick semantics.
It creates no window, content wrapper, input handler, mask or service connection.

Use `SettingsCard` for cards inside Settings, `StyledRectangle` for internal
content layers, and `BarModuleBase`/`BarActionModuleBase` for bar modules. These
roles remain separate; adding a new screen does not require replacing its
internal containers with panel surfaces.

## PanelSurface API

| Property | Default | Contract |
| --- | --- | --- |
| `variant` | `PanelSurface.Translucent` | `Solid`, `Translucent`, `Glass` enums |
| `visualState` | `PanelSurface.Normal` | `Normal`, `Emphasized`, `Selected`, `Focused`, `Disabled` enums |
| `color` | Theme surface for variant/state | Native writable Rectangle color; assigning it replaces the default binding |
| `baseColor` | Read-only variant surface | Solid: opaque `colLayer0Base`; otherwise `colLayer0` |
| `foreground` | Read-only state content token | Bind content color explicitly; it is not inherited by child text |
| `radius` | `Appearance.rounding.large` | Native writable Rectangle radius |
| `border.width` | `1` | Native border; use `0` for borderless windows |
| `border.color` | `colLayer0Border` | Primary token for emphasized, selected and focused states; writable |
| `width`, `height` | Native Rectangle sizing | Set explicitly or use anchors/Layout |
| `implicitWidth`, `implicitHeight` | `0`, `0` | Set explicitly from content when needed; never inferred from children |
| `clip`, `opacity`, `enabled`, `focus` | Native Qt defaults | Never modified by visual state |

Normal uses the base surface and `colOnLayer0`. Emphasized and focused keep
the surface and use `colPrimary` for the border. Selected uses
`colPrimaryContainer` with the variant's alpha and the matching
`colOnPrimaryContainer` foreground. Disabled keeps the base and uses `colSubtext`.
The caller controls actual input availability with `enabled`; visual state is
explicit to avoid changing existing panels when they disable their contents.
When overriding the background, also choose a matching content color.

No implicit padding or size presets are provided. Content measures itself and
owns its spacing. Avoid deriving an implicit dimension from children anchored
to that same dimension, which creates a sizing cycle. Theme bindings are reactive;
there are no extra color or geometry animations on the primitive. Existing
Appearance transitions and consumer animations continue to apply.

### Solid

```qml
PanelSurface {
    variant: PanelSurface.Solid
    implicitWidth: 320
    implicitHeight: 160
    StyledText {
        anchors.centerIn: parent
        text: "Status"
        color: parent.foreground
    }
}
```

Solid remains opaque even when global transparency is enabled, including selected
state. An explicit `color` override takes precedence, including its alpha.

### Translucent

```qml
PanelSurface {
    id: surface
    Layout.fillWidth: true
    implicitHeight: content.implicitHeight + 32
    ColumnLayout {
        id: content
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
        StyledText { text: "Connections"; color: surface.foreground }
    }
}
```

Translucent uses `Appearance.colors.colLayer0`; with global transparency disabled
it is opaque. It does not set Item opacity, so content stays crisp.

### Glass and external shadow

Inside a window whose bounds reserve enough room for the shadow:

```qml
PanelSurfaceShadow {
    target: glassSurface
    elevation: 1
}
PanelSurface {
    id: glassSurface
    anchors.fill: parent
    anchors.margins: Appearance.sizes.elevationMargin
    variant: PanelSurface.Glass
    radius: Appearance.rounding.windowRounding
}
```

Glass expresses compositor-blur intent. Its surface is identical to Translucent:
it falls back to an opaque surface when transparency is off and to an ordinary
translucent surface when compositor blur is off. It neither detects nor enables
blur. Hyprland's blur settings, namespace rules and xray policy remain managed by
`desktop.py` and `LayerEffects`. A QML Rectangle cannot enable independent
background blur for one panel. `StyledBlurEffect` samples wallpaper locally and
has a different purpose; it is not used here.

## Shadow contract

`PanelSurfaceShadow` extends the existing `StyledRectangularShadow`.
Place it **once**, before its target, as a sibling. Never add it alongside another
shadow for the same surface. Keeping it external preserves independent transforms
(for example the sidebar reveal) and avoids adding an invisible content item.

| Property | Default | Contract |
| --- | --- | --- |
| `target` | Required | Rectangle-compatible surface with `radius` |
| `elevation` | `1` | Visual multiplier, not a z coordinate; `<= 0` hides shadow |
| `blur` | `0.9 * elevationMargin * max(0, elevation)` | Writable inherited shadow property |
| `spread` | `max(0, elevation)` | Writable inherited shadow property |
| `offset` | `(0, max(0, elevation))` | Writable inherited shadow property |
| `radius`, geometry | Follow target | Inherited target anchors and radius binding |
| `color`, `cached` | `colShadow`, `true` | Existing shadow defaults |
| `visible` | Positive elevation and visible target | Does not track target opacity; bind opacity when fading |

Elevation 1 preserves the existing shadow defaults. Reserve window margins large
enough for the chosen blur/spread/offset. Ancestor clipping and window bounds can
cut off the shadow; this helper cannot escape them. It does not follow target
transforms or opacity automatically. Copy existing transform/opacity bindings
when migrating, and keep the shadow outside a clipped surface. The window still
owns its input mask, limited to the surface, and its anchor updates. Do not change
namespace rules or global blur configuration as part of a surface replacement.

## Inventario de migración

Auditoría focalizada del 2026-11-03. Las rutas de las tablas son relativas a
`src/quickshell/modules/`, salvo `settings.qml`, relativo a `src/quickshell/`.
`migrado` describe el código: **no** implica validación visual Wayland. Las
sustituciones mantienen IDs, parents/children, máscaras, tamaños, foco, handlers,
clipping, animaciones, capas y sombras. La segunda ola conserva los helpers
`StyledRectangularShadow` existentes, incluidos sus Loaders, opacity y transforms;
no añade sombras ni cambia reglas del compositor.

### Primera ola conservada

| Ruta | Superficie | Estado | Preservación |
| --- | --- | --- | --- |
| `settings.qml` | Fondo raíz | migrado | Sin borde, radio original |
| `desktop/quickPanels/QuickPanel.qml` | `surface` | migrado | Marco compartido, Escape, máscara y resize |
| `desktop/sidebarRight/SidebarRightContent.qml` | `sidebarRightBackground` | migrado | Gaps, tamaños y sombra externa |
| `desktop/sidebarLeft/SidebarLeft.qml` | `sidebarLeftBackground`, `detachedSidebarBackground` | migrado | Reveal/transform independientes; detached cuadrado y sin borde |
| `desktop/dock/Dock.qml` | `dockVisualBackground` | migrado | Márgenes, offsets y sombra |
| `desktop/tailscale/TailscaleWindow.qml` | `surface` | migrado | Máscara, foco y Escape |

### Grupo A: paneles, barras y menús

| Ruta | Superficie | Estado | Preservación / límite |
| --- | --- | --- | --- |
| `desktop/bar/ConfiguredBarContent.qml` | `drawer` / `bar-editor-drawer` | migrado | Misma identidad, posición top/bottom, tamaño y visibilidad; sin sombra añadida |
| `desktop/bar/BarContent.qml` | `contextBackground` | migrado | Conserva `contextSurface` para máscara, foco y menú de clic derecho |
| `desktop/bar/ConfiguredBarContent.qml` | Fondo configurable sin ID | migrado | `showBackground`, borde 0/1, altura y radio condicionales |
| `desktop/bar/LegacyBarContent.qml` | `barBackground` | migrado | Color on/off y shadow Loader intactos |
| `desktop/verticalBar/VerticalBarContent.qml` | `barBackground` | migrado | Orientación, cornerStyle y shadow Loader intactos |
| `desktop/bar/StyledPopup.qml` | `popupBackground` | migrado | Override opaco `m3surfaceContainer`; default contentItem, children y anchors intactos |
| `desktop/bar/RecordingButton.qml` | `popupBackground` / `recording-menu-surface` | migrado | PopupWindow, Region, anchor y acciones start/pause/stop intactos |
| `desktop/bar/SysTrayMenu.qml` | `popupBackground` | migrado | StackView, clip, fade, Behaviors y sombra sincronizada intactos; interacción Wayland pendiente |
| `desktop/cheatsheet/Cheatsheet.qml` | `cheatsheetBackground` | migrado | Region, teclas, medidas y sombra originales |
| `desktop/wallpaperSelector/WallpaperSelectorContent.qml` | `wallpaperGridBackground` | migrado | Foco, teclado, márgenes, layout y sombra originales |
| `desktop/onScreenKeyboard/OnScreenKeyboard.qml` | `oskBackground` | migrado | Sin borde; Region, padding, tamaños, Escape y sombra originales |

### Grupo B y hallazgos de la auditoría

| Ruta | Superficie | Estado | Decisión |
| --- | --- | --- | --- |
| `desktop/mediaControls/MediaControls.qml` | `placeholderBackground` sin reproductor | migrado | Panel popup independiente; sin borde, radio y sombra originales |
| `desktop/onScreenDisplay/OsdValueIndicator.qml` | `valueIndicator` | migrado | Superficie OSD externa; cápsula sin borde, medidas por contenido |
| `desktop/overview/OverviewWidget.qml` | `overviewBackground` | migrado | Override `colBackgroundSurfaceContainer`, sin borde; distribución y sombra intactas |
| `desktop/overview/SearchWidget.qml` | `searchWidgetContent` | migrado | Mismo override, sin borde; shader/OpacityMask, clip, radio y animación intactos |
| `desktop/dock/DockApps.qml` | `popupBackground` de miniaturas | migrado | Override opaco `m3surfaceContainer`, sin borde; fade, hover y tamaños animados intactos |
| `desktop/overlay/OverlayTaskbar.qml` | Raíz | migrado | Taskbar flotante; override opaco y borde `colOutlineVariant` originales |
| `desktop/bluetooth/BluetoothPairingPrompt.qml` | Formulario interno | excluido | Prompt dentro del contenido de Bluetooth; no es marco externo y conserva su borde semántico primary |
| `shared/primitives/common/Toolbar.qml` | `background` | excluido | Control compuesto interno con su propio contrato de toolbar/aliases; no se amplía el rol de PanelSurface a controles |
| `shared/primitives/dialogs/WindowDialog.qml` | `dialogBackground` | migrado | Solo superficie modal: override opaco `m3surfaceContainerHigh`, sin borde; scrim y animaciones intactos |
| `shared/widgets/SelectionDialog.qml` | `dialog` | migrado | Solo superficie del diálogo, opaca y sin borde; scrim y selección intactos |
| `desktop/mediaControls/PlayerControl.qml` | `background` con carátula | pendiente | Superficie especializada con paleta por imagen, blur local y OpacityMask; necesita prueba de composición/render antes de migrar |
| `desktop/overlay/OverlayBackground.qml` | Backdrop fullscreen | excluido | Fondo de overlay, no contenedor de panel |
| `desktop/sidebarRight/todo/TodoWidget.qml` | `dialog` de añadir tarea | migrado | Hallazgo equivalente a SelectionDialog: solo superficie modal, override opaco y sin borde; scrim, contenido y acciones intactos |

### Exclusiones por rol

| Ruta / ámbito | Superficies | Estado | Justificación |
| --- | --- | --- | --- |
| `shared/primitives/common/StyledComboBox.qml` | Control y popup de selección | excluido | Parte del contrato visual/input de un control; no una ventana de aplicación |
| `shared/widgets/NotificationGroup.qml` | `background` de notificación | excluido | Tarjeta con drag/dismiss, temporización y tratamiento propio |
| `desktop/sidebarRight/todo/TodoWidget.qml` | Scrim, controles y contenido restantes | excluido | Solo el marco modal se migra; las capas internas conservan su rol |
| `desktop/sidebarLeft/AiChat.qml` | Burbujas y tarjetas | excluido | Contenido interno, no superficie de ventana |
| `desktop/wallpaperSelector/WallpaperDirectoryItem.qml` | Item y máscara de imagen | excluido | Tarjeta/item interactivo y máscara decorativa |
| `desktop/network/NetworkPanelContent.qml` | Aviso de checkpoint y cards | excluido | Aviso semántico y SettingsCards internos; no marco externo |
| `desktop/cheatsheet/CheatsheetKeybinds.qml` | ScrollEdgeFade | excluido | Gradiente decorativo, no contenedor |
| `desktop/bar/NotificationUnreadCount.qml` | `notifPing` | excluido | Badge semántico |
| `windowsStyle/looks/*` | AcrylicRectangle, BodyRectangle, WPane y derivados | excluido | Lenguaje visual propio; requiere decisión de diseño independiente |
| `desktop/overlay/OverlayBackground.qml`, scrims de diálogos | Backdrops | excluido | Atenuación/fondo fullscreen, no superficie de contenido |
| `../killDialog.qml`, `../welcome.qml`, lockscreen | Fondos especializados | excluido | Fuera de esta migración; cierre de procesos, bienvenida y bloqueo tienen contratos propios |

Esta ola migra **20 superficies en 19 archivos**: los 11 candidatos del grupo A,
8 del grupo B y el diálogo de Todo. No se modifica nuevamente la primera ola.
La lista no implica que cada Rectangle o cada token de superficie deba usar
PanelSurface. El pendiente de código identificado es PlayerControl; las pruebas
visuales en sesión de todos los consumidores siguen siendo responsabilidad
compartida con el usuario, que es el tester principal.

For another migration, inspect the current diff first, replace only the surface
and optionally its shadow, then remove only redundant decoration bindings.
Preserve IDs, explicit radii, margins, parents, masks, focus, keyboard handlers,
transforms, opacity bindings and animations. Keep custom color/border overrides
when they express intentional policy. Do not move content into a wrapper.

## Verification

Run the isolated Qt regression with:

```bash
python3 -m unittest discover -s tests -p test_panel_surface.py -v
```

It compiles the actual three primitive sources with a mock Appearance singleton,
without services or user preferences. It checks variants, transparency on/off,
light/dark theme rebinding, visual states and foreground pairs, native overrides,
anchors, Layout sizing, arbitrary children, zero implicit sizes and shadow
geometry/elevation. Each offscreen process has a 15-second limit. It does not
validate compositor blur, GPU shadow rendering or perceptual contrast in actual
Matugen themes.

Run existing quick panel, settings navigation, audio and bar layout tests in a
Wayland session for integration coverage. The user remains the primary visual
tester: check light/dark Matugen themes, transparency on/off, compositor blur
on/off, sidebar reveal/detach, dock positioning, Settings and Tailscale Escape,
and QuickPanel switching/resizing. Agent checks do not substitute for these
session checks.

### Verificación de la segunda ola

```bash
python3 -m unittest discover -s tests -p 'test_panel_surface*.py' -v
```

`test_panel_surface_migrations.py` valida referencias de máscaras/foco/aliases,
colores especiales, ausencia de bordes nuevos y los shadow Loaders originales.
Comprueba sintaxis con Qt 6 en los 19 consumidores y las dos primitivas. Instancia
**ocho declaraciones reales de fondo** del editor/barra legacy/vertical y menús
(contextual, StyledPopup, grabación y bandeja), con medidas de contenido y tokens
mock. Compara geometría y estilo con un Rectangle nativo que tiene la decoración
original, incluso al cambiar orientación. No carga los servicios ni el contenido
de esas ventanas: las pruebas de referencias son estáticas y no sustituyen drag,
foco, nested menus, shaders o interacción en Wayland. Cada intento offscreen y
cada invocación del parser tiene timeout de 15 segundos.

La transición top/bottom/vertical de la bandeja conserva el comportamiento nativo
de anchors, incluida la altura retenida por Qt al cambiar conjuntos de anclajes;
esta migración no intenta corregir ni rediseñar ese comportamiento.

Resultado de esta iteración (2026-11-03):

- **PASSED:** 20 tests (contrato original, cuatro regresiones de migración,
  14 tests del recorder y RecordingSettings offscreen); comparación de los 19
  consumidores con su copia previa, limitada a los cambios de superficie;
  `git diff --check`.
- **PASSED:** sintaxis Qt 6 de todos los consumidores migrados. El barrido completo
  analiza 717 QML y acepta 716.
- **FAILED, preexistente:** el parser rechaza
  `shared/models/LauncherSearchResult.qml`; el archivo es idéntico a HEAD y
  el parser rechaza también esa versión. Se conserva sin cambios.
- **NOT RUN:** nueve pruebas de sesión (recording bar, tint de tray, dos de bar
  layout, bar groups, drag, per-monitor, persistencia y primitives) por falta de
  acceso efectivo a Wayland en el sandbox; se ejecuta el runner con
  `WAYLAND_DISPLAY` ausente para que sus guards las marquen skipped. No hay
  suite dedicada de overview/wallpaper en `tests/`: aquí reciben comprobación
  sintáctica y de contratos, y su interacción/render queda pendiente en sesión.

No se reinicia la shell ni se modifica configuración personal. No se hacen
commits ni se alteran los cambios preexistentes ajenos a las superficies.
