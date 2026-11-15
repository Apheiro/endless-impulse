# Procesos gráficos internos

Settings → Sistema → **Procesos gráficos internos** administra superficies
auxiliares en `special:endless-internal`. Es independiente de
`special:artificial-minimized` y del scratchpad. No inicia ni detiene procesos,
no administra systemd y no ejecuta comandos introducidos desde la interfaz.

## Política y preferencias

El registro integrado `xembedsniproxy` viene habilitado y no se puede duplicar
ni eliminar. Puede deshabilitarse para recuperar sus superficies. Conserva el
arranque existente del puente XEmbed/SNI y sus dependencias Arch/Nix.

Las reglas manuales requieren clase literal, título literal y propósito. Solo
coinciden ventanas flotantes; el registro integrado requiere además X11.
No se seleccionan todas las ventanas de un PID. Se rechazan patrones,
coincidencias duplicadas, campos vacíos, caracteres de control y clases
críticas o principales comunes. Las clases manuales admiten 3–128 letras,
dígitos, puntos, guiones o guiones bajos; el título admite hasta 160 caracteres
y el propósito hasta 240. Máximo: 32 reglas manuales.

Una clase y un título son identificadores, no una prueba universal de que una
ventana es auxiliar. Usar una clase dedicada; las clases desconocidas pueden
pertenecer a aplicaciones principales. No registrar su ventana principal.

Las preferencias se guardan mediante el Config habitual, en
`$XDG_CONFIG_HOME/endless-Impulse/config.json` (por defecto
`~/.config/endless-Impulse/config.json`):

```json
"internalSurfaces": {
  "xembedEnabled": true,
  "rules": [
    {"windowClass": "aux-capture", "title": "Capture holder", "purpose": "Captura auxiliar", "enabled": true}
  ]
}
```

## Integración y recuperación

`InternalSurfaces.qml` carga desde `shell.qml` y también al abrir su página
de Settings. El adaptador `scripts/hyprland/internal_surfaces.py` valida
todo antes de modificar reglas. Registra reglas Lua con nombres estables,
destino especial silencioso y protección de foco. `render_unfocused` permite
feedback de render fuera del workspace visible; no demuestra compatibilidad
de XTest. No se deshabilita la entrada del proxy: este conserva su control de
región de entrada. La regla visual previa de LayerEffects sigue existiendo.

Las reglas se reconstruyen al iniciar y después de `configreloaded`. Las
aperturas de ventanas disparan reconciliación acotada; sus propios movimientos
no la disparan. No hay polling ni reintentos automáticos por fallo. El botón
**Actualizar / reintentar** permite recuperar una operación fallida.

El estado por sesión se guarda atómicamente y con exclusión entre procesos en
`$XDG_STATE_HOME/endless-Impulse/internal-surfaces.json`. Registra la identidad
de cada superficie y su origen antes de moverla. Direcciones reutilizadas no
heredan el origen de otro cliente. Deshabilitar o quitar una regla deshabilita
su regla nativa y restaura las superficies registradas, sin solicitar foco.
La restauración es de workspace; no promete restaurar geometría exacta.

Si la regla nativa dirige una ventana recién creada antes de observar su
origen, se usa el workspace ordinario activo al restaurarla. Un fallo conserva
la información de recuperación para reintentar. Si una superficie ya fue
restaurada externamente, deshabilitar su regla no la vuelve a mover.

TaskbarApps filtra superficies internas para dock y tareas Windows. Overview
y TaskView aplican el mismo filtro. WindowMinimizer rechaza estas superficies.
La lista cruda de HyprlandData permanece completa para el inventario. Un
selector externo que enumere clientes necesita su propio filtro; no se
modifican programas externos.

## Aplicación y validación manual

El contexto runtime registrado apunta al checkout actual, con lanzador Nix.
Ese registro no prueba qué código está cargado actualmente. No se reinició
Quickshell ni Hyprland. Si la instancia usa una copia anterior instalada,
la nueva UI requiere cargar el checkout mediante el flujo de desarrollo del
proyecto, no copiar archivos a la configuración personal. Abrir `./dev settings`
carga esta página; habilitar su regla aplica el administrador. Usar
`./dev restart` solamente cuando se autorice reiniciar la instancia.

Para una aplicación manual acotada, desde la raíz del repositorio:

```bash
python3 src/quickshell/scripts/hyprland/internal_surfaces.py apply --state /tmp/endless-internal-manual.json
```

Este comando, sin `--config`, solo aplica el registro integrado y guarda su
origen. Para revertirlo con ese mismo estado:

```bash
python3 src/quickshell/scripts/hyprland/internal_surfaces.py restore-xembed --state /tmp/endless-internal-manual.json
```

Si el servicio ya está cargado, deshabilitar primero su registro en Settings
para evitar que una reconciliación posterior vuelva a aplicar la preferencia
habilitada. La recuperación CLI no modifica preferencias. Si falla, conserva
el estado y muestra el error; no borrar el archivo de recuperación.

Comprobar con `hyprctl -j clients` que únicamente el contenedor esperado está
en `special:endless-internal`. Verificar dock, tareas y overview. Observar
refresco del icono legado y probar manualmente clic izquierdo sobre pamac-tray
(abre Pamac); no asumir que su clic derecho tiene menú SNI. Verificar que foco
y puntero no cambien inesperadamente. Si hay una regresión, deshabilitar el
registro y restaurar antes de seguir. No se realizaron clics automáticos.

## Resultado del agente (2026-11-09)

- **PASS:** 14 pruebas en `test_internal_surfaces*.py`: política, idempotencia,
  restauración, fallos explícitos y silenciosos, recuperación de reglas
  eliminadas, restauración externa, identidad reutilizada, separación de
  ventanas del mismo PID y protección de minimizadas/agrupadas/ancladas.
- **PASS:** página y servicio QML reales, sin compositor, con IPC simulado y
  preferencias aisladas: controles Agregar, rechazo de clases críticas,
  persistencia, habilitación/deshabilitación, eliminación y filtros.
- **PASS:** parser `qmlformat` de Qt 6 sobre los nueve QML afectados,
  `py_compile` y `git diff --check`. Las herramientas homónimas de `/usr/bin`
  son Qt 5 y no sirven para estos archivos Qt 6.
- **PASS:** lectura en vivo, antes y después: `xembedsniproxy`, PID 2531,
  dirección `0x55f6d762f1d0`, mapped/floating/X11, workspace `2`.
- **PASS (seguimiento):** aplicación nativa y movimiento en vivo sin reinicios.
  La primera ejecución reveló que el match Lua usa `float`, no `floating`
  (este último pertenece al JSON de clientes). Corregido el generador,
  conservando ambas protecciones, nativa y Python; las 14 pruebas siguen pasando.
  El verificador reversible movió únicamente xembedsniproxy, PID 2531, de `2`
  a `special:endless-internal`. La lectura independiente posterior confirmó
  el destino, el foco intacto y ausencia de movimientos de otros clientes.
  Snapshot y origen actuales: `/tmp/endless-internal-live-before.json` y
  `/tmp/endless-internal-live-state.json`. La evidencia del intento fallido,
  revisada sin movimientos ni cambios de foco, se conservó en
  `/tmp/endless-internal-failed-floating-20261109T132021622131Z/`.
  Para deshacer esta aplicación acotada usar Settings → Deshabilitar y restaurar
  o el comando `restore-xembed` con `--state /tmp/endless-internal-live-state.json`.
- **SKIP:** compatibilidad funcional de XEmbed/XTest y refresco real con
  workspace cerrado, y comprobación visual en temas claro/oscuro. La prueba
  fuera de pantalla verifica carga y acciones, no apariencia ni interacción
  con el icono real.
