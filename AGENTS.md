# Proyecto
Endless Impulse: escritorio Hyprland/Wayland, fork de illogical-impulse, con dependencias upstream independientes. Interfaz: Quickshell (Qt 6, QML y JavaScript); configuración: Lua; integración: Bash y Python; temas: Matugen; fórmulas: MathJax/Node.js.

# Estructura
- `src/quickshell/`: fuente QML/JS independiente de la instalación. `modules/desktop/` (interfaz principal), `modules/windowsStyle/` (variante), `modules/shared/` (widgets comunes), `modules/settings/` (ajustes), `shellVariants/` (composición de layouts), `services/` (estado), `scripts/` (integraciones).
- `config/xdg/config/` y `config/xdg/data/`: recursos desplegables a rutas XDG.
- `config/xdg/config/hypr/`: ventanas, atajos y arranque.
- `installer/commands/`, `installer/distros/`, `installer/lib/`: instalación; `config/variants/`: variantes.
- `runtime/math/` y `runtime/python/`: dependencias de ejecución.
- `tests/`, `docs/`: validación y documentación. Ver `docs/architecture/overview.md`.
- `setup`: instalación, actualización y desinstalación.
- `packaging/nix/`, `flake.lock`: entorno reproducible; `installer/dependencies/arch.json`: paquetes normales de Arch.

# Trabajo
- Seguir las convenciones existentes; mantener cambios enfocados y conservar licencias y atribuciones.
- Desarrollar con `./dev run`, `./dev settings` y `./dev check`; QML se recarga al guardar. `./dev restart` reinicia esta instancia. No actualizar locks sin necesidad; revisar errores y comprobar la función modificada.
- La ejecución usa la sesión y preferencias del usuario; no es una prueba aislada. No ejecutar `./setup install` ni reemplazar configuraciones personales sin una solicitud explícita.
- Consultar `.github/CONTRIBUTING.md` y `docs/development/deps-info.md` para desarrollo y dependencias.
- El usuario es el tester principal; distinguir las verificaciones del agente de las pruebas y validaciones del usuario.
- Pruebas temporales: restauración idempotente y estado de resolución explícito. No perder Revertir/Confirmar durante consultas ni reintentar en bucle al vencer el contador; ante un fallo conservar la copia previa y ofrecer reintento manual. Probar error, vencimiento y restauración externa.

# Interfaz
- Reutilizar `qs.modules.shared.widgets` y tokens de `Appearance` para colores Matugen, texto, tamaños, radios, sombras y animaciones; evitar valores visuales fijos salvo indicadores semánticos (p. ej., grabación roja).
- Usar una única carpeta `modules/shared/primitives/{common,settings,dialogs,bar}` para bases visuales, interactivas y contenedores; mantener los widgets compuestos y la lógica de funciones fuera. Importar el ámbito correspondiente; ver `docs/development/primitives.md`.
- Los módulos de barra usan `BarModuleBase`/`BarActionModuleBase`; el registro solo carga componentes. Fondos, radios, estados y estilo Pills/Line-separated pertenecen a la base; desactivar `surfaceVisible` en controles embebidos para evitar capas duplicadas. Espacios y separadores son elementos de layout.
- El padding interno de las cards de barra se define únicamente en `BarModuleBase` con `Appearance.sizes.barModulePadding`. Los contenidos no agregan márgenes exteriores ni inflan su ancho para simular padding; solo gestionan separaciones entre elementos internos.
- Pills agrupa módulos visibles contiguos según su posición, sin depender de su tipo; espacios/separadores cortan el grupo. Extremos expuestos plenamente redondeados, esquinas interiores levemente redondeadas y gaps transparentes, sin líneas. Respetar transparencia del tema y padding dentro de la altura útil de barra, sin invadir sus márgenes flotantes.
- Corregir inconsistencias en el componente compartido; evitar estilos locales duplicados. Mantener márgenes, alturas y estados coherentes entre paneles equivalentes.
- Sonido, red y Bluetooth deben compartir estilo de iconos, tamaño, grosor, burbuja y área de clic en la barra.
- Combinar fondo y texto con los pares superficie/contenido del tema en cada estado (normal, hover, seleccionado y deshabilitado); verificar contraste en temas claros y oscuros.
- Usar `colLayer0` como superficie base y `colLayer0Border` como borde. `colLayer1/2/...` son capas de superposición: no usarlas solas sobre una ventana transparente. Respetar la transparencia configurada; tomar menús existentes como referencia (p. ej., `SysTrayMenu.qml`).
- Usar `SettingsCard` para cards dentro de Settings y `SegmentedControl` para grupos principales; conservar `colLayer0` como base de ventanas y popups.
- Settings y paneles deben respetar la misma política de transparencia; no forzar superficies opacas. Transparencia y blur son ajustes distintos.
- En popups, reservar margen para `StyledRectangularShadow` y limitar la máscara a la superficie. Anclar con `item` o `window`, nunca ambos; actualizar el anclaje al abrir/cambiar tamaño. Comprobar el namespace del panel y las reglas `blur`/`blur_popups` de Hyprland antes de añadir efectos o cambiar ajustes globales.

- Las animaciones usan las duraciones/velocidades de `Appearance`; para tiempos visuales propios, aplicar `Appearance.animationDuration(ms)` una sola vez. Respetar `appearance.animationSpeed`; `AnimationSpeed` sincroniza también las animaciones de Hyprland sin modificar sus archivos; no escalar relojes, temporizadores ni esperas de servicios.
- Elegir controles según el dato: sliders con entrada exacta para rangos continuos, controles numéricos para cantidades, campos de una línea para rutas/fuentes/URLs y multilínea solo para contenido largo. Mostrar unidades y límites; no guardar valores al inicializar controles.
- Barra: clic izquierdo abre/cierra el lateral derecho; clic derecho abre los controles rápidos. Los accesos avanzados a Settings usan los botones personalizables existentes del lateral (su acción de menú), sin añadir accesos duplicados ni incluirlos en los menús rápidos. Reutilizar servicios y lógica entre ambas vistas. Sonido, red y Bluetooth comparten una sola ventana `QuickPanel`, coordinada por `QuickPanelState`; cambiar contenido sin recrear el marco.
- Edición de barra horizontal: clic derecho en espacio libre → Editar barra. `BarLayout` mantiene un borrador por identidad: fila libre (`items`), espacios fijos/flexibles y un ancla opcional al centro exacto (`centerKey`); Cancelar descarta. Migrar las tres zonas antiguas al leer, sin sobrescribir preferencias antes de Guardar. Conservar los menús propios de los widgets y la distribución original mientras `bar.layout` sea `null`.
- Con `bar.independentLayouts`, leer/guardar `bar.layoutsByScreen` por nombre de monitor; el borrador solo afecta su pantalla. Mantener `bar.layout` como diseño compartido y fallback sin borrar perfiles al cambiar de modo; `null` por monitor restaura su distribución original.
- En edición, mostrar módulos reales con una capa de arrastre que intercepte sus acciones; tooltips ligados al hover explícito (`containsMouse` en `MouseArea`) y resaltado solo al seleccionar o arrastrar. La barra anima en QML; evitar animaciones del compositor al ampliar su superficie.
- Arrastre de barra: preview atenuada del módulo real con captura fija, hueco de su ancho en destino y desplazamiento con animaciones de `Appearance`. Conservar el delegado que tiene el mouse y proyectar la distribución sin mutar el borrador hasta soltar; devolverlo al catálogo lo quita del borrador. Cancelar no cambia preferencias.

# Git
- El agente gestiona Git. Acumular cambios sin commitear hasta que el usuario lo indique explícitamente; agruparlos por propósito en commits coherentes.
- Usar Conventional Commits para releases: `tipo(alcance): resumen` (`feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `build`, `ci`, `chore`; alcance opcional). Marcar incompatibilidades con `!` y explicar `BREAKING CHANGE:` en el cuerpo.
- No crear tags, publicar releases ni hacer push sin indicación del usuario.
