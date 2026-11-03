# Congelamientos al abrir aplicaciones — investigación del 3 de noviembre de 2026

Corrección implementada y verificada en la sesión real mediante el runtime Nix
(Quickshell 0.3.2, Qt 6.12.0). No cambia componentes visuales ni preferencias.

## Explicación sencilla

Al abrir algunas aplicaciones se modifican directorios que Quickshell vigila.
Eso le hace revisar la lista de aplicaciones instaladas, aunque no se haya
instalado nada. Esa revisión publicaba cientos de pasos intermedios. En cada
paso, el buscador volvía a revisar y preparar la lista completa con una búsqueda
de duplicados particularmente costosa. Todo ocurría en el hilo que atiende la
interfaz y el IPC, que quedaban esperando hasta terminar.

Ahora el buscador recibe el catálogo al finalizar la revisión y elimina los
duplicados en una sola pasada. Las categorías usan esa misma lista. La revisión
sigue activa para detectar instalaciones, desinstalaciones y actualizaciones.
El cambio es compartido: no contiene excepciones para Steam o Telegram.

## Evidencia y cadena causal

1. Una sonda sin ventanas observó `DesktopEntries.applications.valuesChanged`
   y `DesktopEntries.applicationsChanged`; `inotifywait` registró los eventos de
   los directorios padre que también vigila Quickshell.
2. Al abrir Telegram se observó `ATTRIB,ISDIR` sobre
   `~/.local/share/TelegramDesktop`. Al abrir Steam se observaron eliminación y
   creación de `~/.steampath` y `~/.steampid`, además de escrituras de
   `~/.pulse-cookie`.
3. El monitor de Quickshell vigila los directorios de aplicaciones **y sus
   padres**, incluyendo el directorio personal. Un evento en esos padres provoca
   un escaneo completo tras su temporizador de 100 ms. No necesita un cambio en
   un archivo `.desktop` ni una nueva ventana o registro de bandeja.
4. El entorno real contiene `/usr/share` y las rutas de exportación de Flatpak
   repetidas cuatro veces en `XDG_DATA_DIRS`, además de proveedores superpuestos
   de Nix y del sistema. En 0.3.2, el procesamiento de IDs repetidos durante el
   escaneo puede reemplazar objetos nativos aunque el catálogo lógico no cambie.
5. `ObjectModel.diffUpdate()` publica `valuesChanged` por cada inserción y
   eliminación. La sonda registró **542 notificaciones por escaneo**, con **299
   aplicaciones finales, cero IDs agregados y cero eliminados**. Su procesamiento
   sin los consumidores del escritorio tomó aproximadamente 0–2 ms.
6. El binding anterior de `AppSearch.list` dependía de cada uno de esos cambios.
   Su `filter` con `findIndex` hacía comparaciones cuadráticas, seguido de la
   preparación de nombres, iconos y categorías. La referencia parcial recuperada
   contiene 354 evaluaciones de la lista y 4.678.698 ejecuciones de la comparación
   interna. Esto amplificaba un escaneo en segundos de trabajo síncrono.

El código de la versión exacta respalda la secuencia:
[monitor](https://github.com/quickshell-mirror/quickshell/blob/v0.3.2/src/core/desktopentrymonitor.cpp),
[escaneo y publicación final](https://github.com/quickshell-mirror/quickshell/blob/v0.3.2/src/core/desktopentry.cpp),
[modelo y notificaciones por fila](https://github.com/quickshell-mirror/quickshell/blob/v0.3.2/src/core/model.hpp).
No se atribuye el problema a Hyprland, a PanelSurface ni al protocolo gráfico.

## Solución y decisiones

- `src/quickshell/services/AppSearch.qml`: publica una lista desde el evento
  `DesktopEntries.applicationsChanged`, que llega al terminar el escaneo. También
  obtiene el catálogo al inicializarse, por si el servicio se carga después del
  escaneo inicial. Deduplica por ID con `Set`, manteniendo la primera entrada y el
  orden recibido. Conserva objetos `DesktopEntry` nativos y sus notificaciones
  de metadatos, ejecución y acciones.
- `src/quickshell/services/LauncherSearch.qml`: calcula categorías a partir de
  `AppSearch.list`, evitando procesar los estados parciales del modelo nativo.
  Se preservaron los cambios de clipboard preexistentes de este archivo.
- `tests/test_app_search.py`: integración con Quickshell real, 320 entradas
  artificiales, rutas XDG repetidas, prioridades y preferencias temporales.
- Este documento: diagnóstico, resultados, reproducción y límites.

Se evaluaron alternativas: cambiar solamente la deduplicación dejaría cientos de
reconstrucciones de los índices; un temporizador adicional introduce demora y
complica la vida útil de objetos que el escaneo elimina. El evento final nativo
permite actualizar antes de esa eliminación. Desactivar el monitor o conservar
un catálogo fijo perdería actualizaciones. Filtrar eventos o corregir la
publicación en C++ sería una mejora upstream posible, pero exigiría cambiar la
dependencia y no sustituye la necesidad de consumir correctamente sus cambios.
No se modificaron Quickshell, Hyprland, el entorno XDG ni los locks.

## Mediciones de la sesión real

Cada ensayo sin profiler duró aproximadamente 10 s. Se lanzó la aplicación
aproximadamente al segundo 1 y se consultó `health ping` cada 120 ms después de
completar la consulta anterior, con un timeout de 600 ms. CPU significa tiempo
**del proceso Quickshell**, usuario + sistema, leído de `/proc/PID/stat` con
resolución de 10 ms; incluye el trabajo normal del escritorio durante el ensayo.
No es tiempo de CPU de Steam o Telegram ni duración total de su arranque.

| Ensayo sin profiler | CPU antes → después | IPC vencidos antes → después | Máxima latencia IPC después |
| --- | --- | --- | --- |
| Abrir Telegram | 4.180 → 400 ms | 5 → 0 | 40,50 ms |
| Abrir Steam | 4.500 → 480 ms | 5 → 0 | 50,20 ms |
| Reabrir Telegram existente, después | 360 ms | 0 | 115,59 ms |
| Reabrir Steam existente, después | 90 ms | 0 | 37,78 ms |

La CPU de los ensayos de apertura bajó aproximadamente **90 %**. El mayor
intervalo entre respuestas IPC exitosas pasó de 4,036 a 0,160 s para Telegram y
de 4,258 a 0,171 s para Steam. Estos intervalos incluyen el período de muestreo:
no son una medición exacta de la duración de un frame congelado.

Otras repeticiones estables tampoco tuvieron IPC vencidos: Telegram 360 ms de
CPU/máximo 47,21 ms IPC; Steam 2.110 ms de CPU/máximo 102,47 ms IPC. Hay variación
de carga y actividad de la aplicación; no se presenta únicamente el mejor caso.
Se descartó como comparación estable un ensayo inmediatamente posterior al
hot reload, que coincidió con la reinicialización de otros servicios.

### QML Profiler oficial

Se hicieron nuevas capturas completas con `qmlprofiler`, con la instancia real
del escritorio iniciada mediante `./dev run --debug 39576`. La grabación se activó
después de cargar la shell; se incluyeron binding, handling signal y JavaScript.

| Métrica | Telegram, referencia parcial | Telegram corregido | Steam corregido |
| --- | --- | --- | --- |
| Evaluaciones de `AppSearch.list` | 354 | 1 | 1 |
| Evaluaciones de `preppedNames` | 354 | 2 | 2 |
| Evaluaciones de `preppedIcons` | 353 | 1 | 1 |
| Evaluaciones de `appCategories` | 354 | 1 | 1 |
| Tiempo instrumentado inclusivo de `list` | 1.879,763 ms | 6,308 ms | 6,146 ms |
| Tiempo CPU del proceso en captura nueva | no comparable | 340 ms | 450 ms |
| IPC vencidos en captura nueva | referencia: varios | 0 | 0 |
| Máximo IPC en captura nueva | referencia: varios timeouts | 33,23 ms | 48,59 ms |

El antiguo callback de comparación por `findIndex` desapareció. La actualización
completa con `Set` se ejecutó una vez en cada captura nueva. `preppedNames` aún
puede reaccionar a un cambio real de metadatos nativos antes de recibir la nueva
lista; por eso se observaron dos evaluaciones, no una.

Los tiempos del profiler tienen sobrecarga y son inclusivos: **no deben sumarse**.
Además, tanto la referencia como algunas entradas de las nuevas capturas
contienen duraciones negativas, incluso en `appCategories`; no se usan esos
valores para calcular mejoras. Los conteos, la CPU y la latencia IPC aportan
verificaciones independientes. La referencia de 397 MB está truncada: sus
conteos son los eventos recuperables, no necesariamente todo el bloqueo.

## Regresión y seguridad

Resultados del agente:

- `./dev check -p test_app_search.py`: pasó. Comprueba catálogo inicial,
  deduplicación, Hidden/NoDisplay, prioridades XDG, cientos de cambios de filas
  con una publicación por escaneo completo, categorías, búsqueda normal y
  aproximada, resultados y acciones del launcher, iconos, instalación,
  actualización de nombre/icono/categorías/keywords/acciones, desinstalación,
  retorno a una entrada de menor prioridad y ejecución del objeto nativo.
- Control negativo con una copia aislada de `AppSearch` anterior: rechazado por
  timeout IPC de 3 s. No se restauró código antiguo sobre la sesión del usuario.
- `./dev check -p 'test_icon*.py'`: 14 pruebas pasaron, incluyendo el flujo QML
  de preview/aplicación/reset y resolución viva de iconos.
- `./dev check -p test_dock_thumbnails.py`: pasó captura, pausa, actualización y
  liberación de miniaturas del Dock sobre una ventana de prueba propia.
- `git diff --check`: pasó.

Las sondas no tenían ventanas ni registraban el runtime de la sesión. Los
reinicios reales se hicieron cerrando solo la configuración registrada,
arrancando mediante el wrapper Nix `./dev run`, capturando y cerrando la instancia
de depuración, y recuperando con `./dev run -d`. Al finalizar se confirmó una
sola instancia normal de esta configuración, sin `--debug`, y respuesta literal
`ok` de `health ping`. Una primera automatización intentó medir antes de terminar
el arranque; ese intento se descartó y se completó la recuperación. Los siguientes
intentos esperaron además el mensaje `Configuration Loaded`.

No hubo instalación de herramientas, cambios de configuración personal, commits,
reset, checkout masivo ni cambios visuales. Las pruebas de interfaz del agente
no reemplazan la validación visual y de uso cotidiano del usuario.

## Evidencias y límites pendientes

Referencia conservada: `/tmp/qs-profile-20261103/telegram.qtd` y `samples.json`.
Lectura en streaming: no se cargó todo el XML en memoria.

Nuevos archivos: `/tmp/qs-investigation-20261103/`:

- `baseline-{telegram,steam}.json`: comparación sin profiler anterior al cambio.
- `final-{cold,reopen}-{telegram,steam}.json`: comprobación final sin profiler.
- `fixed-profile-{telegram,steam}-full.qtd`: capturas nuevas completas.
- `baseline-summary.txt`, `fixed-telegram-full-summary.txt`,
  `fixed-steam-summary.txt`: conteos extraídos; conservar la advertencia sobre
  duraciones negativas.
- `probe.log`, `inotify.log`: notificaciones y disparadores observados.
- `measure.py`, `profile.py`, `summarize.py`: scripts de esta investigación.
- `negative-control.log`: regresión al usar el código anterior aislado.

La corrección no evita escaneos innecesarios dentro de la dependencia ni sus
notificaciones por fila. Reduce su amplificación en los servicios afectados.
El monitor nativo sigue definiendo qué cambios de archivos detecta: se verificó
instalación/actualización atómica y desinstalación, no se amplió la vigilancia
upstream a ediciones de contenido en sitio. No se midió una sesión WindowsStyle
completa ni bibliotecas de miles de aplicaciones. Otras causas de bloqueos y
picos de CPU siguen siendo posibles. La estabilidad prolongada y la validación
visual final corresponden al usuario.
