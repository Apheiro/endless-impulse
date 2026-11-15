# Contrato IPC endless-storage v1

Proceso interactivo de larga vida, JSON Lines UTF-8 por stdin/stdout, una línea
por frame. **Stdout contiene exclusivamente JSON**, sin banners ni logs. No hay
exportación del árbol. Las solicitudes requieren `id` string no vacío (máximo
128 bytes); el cliente debe usar IDs únicos durante la conexión. No se interpreta
ningún texto como comando. No se ejecutan subprocesses en producción.

Todas las respuestas/eventos incluyen `protocol: 1` y `type`. Una solicitud válida
recibe exactamente una respuesta con su `id` y `ok`; un scan además produce
eventos. Una solicitud malformada produce `ok:false,id:null,error.code`, sin
abortar el proceso ni repetir el payload. Se rechazan campos desconocidos, tipos
incorrectos, números negativos y acciones desconocidas. Campos opcionales que
no correspondan a la acción se ignoran. No se envía un saludo inicial.

Límites: 65 536 bytes por línea de entrada (incluido newline), raíz de hasta
16 384 bytes, 262 144 bytes por respuesta/evento sin newline, páginas de 1 a 128
filas (64 por defecto). Frames de entrada excesivos se consumen hasta newline y
responden `frame_too_large`. Una respuesta demasiado grande se sustituye por
`response_too_large` conservando el `id`; reducir `limit` y usar `node_id`. Los
casos extremos de nombres/rutas/errores pueden exceder incluso una página mínima;
el error es explícito y no borra el detalle del snapshot. No hay frames ocultos
con continuaciones del árbol. La cola stdin tiene ocho frames como máximo.

## Solicitudes

| action | Campos | Resultado |
| --- | --- | --- |
| `scan` | `root` **o** `root_hex`, opcional `workers` (1–4) | Ack inmediato con `scan_id` y estado; reemplaza el scan anterior |
| `status` | ninguno | Estado actual y contadores, o `idle` |
| `progress` | ninguno | Mismo contenido que `status`; también hay eventos automáticos |
| `browse` | `scan_id`, opcional `path` **o** `path_hex` **o** `node_id`, `offset`, `limit`, `sort`, `chart_width`, `query`, `others`, `directories_only` | Una página del snapshot terminado |
| `cancel` | `scan_id` | Cancelación cooperativa; idempotente para ese scan |
| `close` / `shutdown` | ninguno | Ack `closed`, cancela y termina el proceso |

`scan_id` es opaco, único por generación y sesión. `cancel` y `browse` lo requieren
para no afectar otro disco/scan: `stale_scan` si no coincide. `status` informa
siempre la generación actual. `node_id` solo vale dentro de su `scan_id`; nunca
reutilizarlo en otra generación. Una nueva solicitud `scan` invalida inmediatamente
la navegación del snapshot anterior, incluso si la raíz nueva luego falla.

`root` es una ruta absoluta del filesystem Linux, sin componentes symlink ni
`..`. `root_hex` codifica los bytes de la ruta absoluta para nombres no UTF-8.
Validar la forma de la raíz precede al ack; abrirla ocurre en el worker. Una raíz
inexistente, archivo o inaccesible recibe ack y luego evento terminal `failed`.

`path` es relativo a la raíz, vacío significa raíz. `path_hex` es su equivalente
en bytes. Se rechazan campos de ruta simultáneos y `node_id` junto a una ruta.
`node_id` evita resolver nombres y es la opción preferida para navegación.
`sort`: `size_desc` (predeterminado), `size_asc`, `name`; tamaños empatados se
ordenan por nombre crudo. La fila sintética de archivos usa nombre de orden vacío,
por lo que aparece primero en orden `name`. `offset` es índice, no cursor de FS;
se limita a la cantidad total de filas. El snapshot es inmutable durante paginado.

### Agregación para Settings

La extensión aditiva del v1 admite `chart_width` entero (240–4000, default 800),
`query` texto, `others` booleano y `directories_only` booleano. Los defaults
preservan el paginado original, incluida la fila sintética de archivos.

Cada browse devuelve `segments`: hasta siete nodos de directorio prominentes por
bytes, seguidos opcionalmente de `{type:"others", allocated_bytes, count}`.
Se usa la totalidad de hijos directos, independiente del sort, query y página;
el umbral es `total_bytes × max(0.012, 22/chart_width)`. `others:true` pagina solo
los hijos fuera de esos segmentos individuales. `query` filtra nombres de
presentación sin distinguir mayúsculas; `directories_only:true` omite la fila
sintética. `total_children` y `next_offset` corresponden al resultado filtrado.
`directory_count` informa todos los hijos directorio; `chart_width` informa el
ancho efectivo. Los archivos directos y bloques propios del nodo siguen en
`direct_files_bytes` y `own_bytes`, fuera de `segments`.

Así la UI recibe solo una página y segmentos acotados; no necesita descargar
millones de nodos para calcular «Otros». Al navegar debe conservar `node_id`;
las rutas lossy se usan solo para mostrar, nunca para abrir nombres no UTF-8.

## Configuración de concurrencia

`scan.workers` es opcional, entero 1–4. El default es 2, o el valor válido de
`ENDLESS_STORAGE_WORKERS` configurado al iniciar el ejecutable. La solicitud
expresa tiene prioridad. Entorno inválido usa default 2; solicitud inválida
responde `invalid_workers` sin sustituir el scan actual. `workers:1` es el modo
secuencial recomendado para HDD o limitar I/O. No se promete autodetección SSD.

Los helpers se crean cuando hay un subárbol para repartir después de descubrir
16 directorios o procesar 256 archivos; un árbol pequeño permanece secuencial.
Cola acotada a `2*workers`; el exceso se recorre por DFS local. Cada tarea tiene
un descriptor previamente validado; los workers comparten dedup de hardlinks,
pero no streams readdir. Un scan no publica hasta terminar/cerrar todo su pool.
Los IDs de nodos pueden variar entre scans/worker counts; tamaños y atribución
por ruta de hardlinks son deterministas en un filesystem estable. El orden de
paginación conserva desempate por nombre crudo, sin depender de los IDs.

## Clasificación de incidentes

Delta aditivo de v1, con una corrección semántica deliberada: **modified-only
termina como `finished`**, con `changes_observed:true`. El terminal
`finished-with-warnings` se reserva para omisiones/fallos de cobertura. Se conserva
`issue_count` como total de observaciones e incidencias; ya no debe presentarse
como cantidad de carpetas ilegibles. `issue_count = unstable_entries +
unreadable_count` en el resumen. Exclusiones intencionales no suman issues.

Campos nuevos de `completed.data` para snapshots terminados:

| Campo | Significado |
| --- | --- |
| `unstable_entries` | Observaciones de cambio de directorio, sin errno de lectura |
| `unreadable_count` | Incidencias que impiden asegurar cobertura; incluye omisiones por cambios |
| `excluded_count` | Nodos de directorio y entradas de archivos excluidos intencionalmente; ya existente |
| `changes_observed` | `unstable_entries > 0` |
| `coverage_incomplete` | `unreadable_count > 0`; pérdida de cobertura detectada |
| `coverage_uncertain` | Se observó cambio de mtime de directorio: podría haber entradas no vistas |
| `uncertain_directories` | Cantidad de observaciones con esa incertidumbre |
| `issue_codes` | Histograma exacto `{code: count}`, sin rutas/nombres y sin límite de muestras |
| `execution` | `{workers_limit, workers_used, queue_peak, hardlinks_retained}` |

`workers_used` cuenta el coordinador más helpers creados; no significa que todos
hayan tenido idéntica carga. `hardlinks_retained` cuenta inodes distintos
mantenidos durante el escaneo, antes de liberar la tabla al finalizar. No se
retiene un índice por archivo ordinario en el snapshot. Las métricas no exponen
rutas; el histograma cuenta todo aunque browse limite issues locales a 16 muestras.

| Código | Categoría | Efecto |
| --- | --- | --- |
| `directory_metadata_changed` | `unstable` | Solo ctime cambió, sin mtime ni nlink=0; metadatos/permisos cambiantes, no un fallo de lectura |
| `directory_changed` | `unstable` | mtime cambió; cambios de nombres/entradas posibles, `coverage_uncertain:true` |
| `directory_removed` | `unreadable` | `st_nlink == 0` al finalizar; directorio eliminado/desvinculado |
| `stat_entry` | `unreadable` | fstatat falló; ENOENT también implica una entrada omitida y mantiene warning |
| `open_directory`, `read_directory`, `directory_stat` | `unreadable` | Fallo real de open/readdir/fstat, con errno cuando existe |
| `directory_replaced` | `unreadable` | Identidad dev/ino cambió entre descubrimiento y apertura |
| `depth_limit`, `mount_identity_unavailable` | `unreadable` | No se visitaron hijos o no se pudo garantizar su volumen |

La observación es por directorio, no por archivo modificado. `ctime` puede cambiar
sin afectar la enumeración (p. ej. cambios de metadatos); `mtime` puede indicar
altas/bajas/renombres. Ambos se comprobaban antes con un solo `directory_changed`.
Ahora se separan sin afirmar que una enumeración cambiante sea atómica o completa:
`coverage_incomplete:false, coverage_uncertain:true` significa que **no se observó
un fallo**, pero **podrían faltar entradas**. La UI debe mostrar ese matiz y
permitir reescaneo manual, sin afirmar «todo leído» ni «no se pudo leer» por cada
cambio. Un errno real, incluso causado por un cambio concurrente, no se oculta.
Cambios de contenido de archivos que no alteren metadatos del directorio pueden
no observarse: las sumas siguen siendo una vista temporal de metadatos.

Nodos de browse añaden `unreadable_count`/`unstable_entries` locales,
`subtree_unreadable_count`/`subtree_unstable_entries` de toda la rama,
`changes_observed`, `coverage_incomplete` y `coverage_uncertain` de la rama.
Cada muestra de issue añade `category: "unstable" | "unreadable"`.
`subtree_issue_count` continúa sumando ambas categorías. `complete:false` conserva
su semántica conservadora anterior (cualquier issue o exclusión en ese nodo);
un cambio metadata-only también lo pone a false. Para informar errores de
lectura usar `coverage_incomplete`/`subtree_unreadable_count`; para estabilidad usar
`changes_observed`/`coverage_uncertain`. Una exclusión no es fallo de cobertura de
la política de scan: su nodo se identifica por `exclusion` y `complete:false`.

Ejemplo de terminal modified-only, campos relevantes:

```json
{"protocol":1,"type":"event","event":"completed","request_id":"s","scan_id":"S","seq":3,"state":"finished","data":{"issue_count":783,"unstable_entries":783,"unreadable_count":0,"excluded_count":4,"changes_observed":true,"coverage_incomplete":false,"coverage_uncertain":true,"uncertain_directories":783,"issue_codes":{"directory_changed":783},"execution":{"workers_limit":2,"workers_used":2,"queue_peak":4,"hardlinks_retained":10}}}
```

Los números son ilustrativos, no un diagnóstico de los 783 incidentes del usuario.
El histograma de una futura ejecución elegida por el usuario permitirá conocer
su composición sin exponer rutas en eventos globales.

## Estados y eventos

Estados: `idle`, `queued`, `scanning`, `cancelling`, `finished`,
`finished-with-warnings`, `aborted`, `failed`. Solo los dos `finished*` permiten
navegar. `finished-with-warnings` es una visita terminada con carpetas/entradas
incompletas identificadas, no una garantía de total completo. `finished` puede
contener cambios observados e incertidumbre: consultar los campos de clasificación.

Los eventos incluyen `request_id` de la solicitud `scan`, `scan_id`, `seq`
creciente dentro de esa generación, `state` y `data`:

- `progress` aproximadamente cada 250 ms mientras está activo, sin porcentaje.
- `completed` una vez por generación que termina con conexión abierta: éxito,
  advertencias, fallo o cancelación/sustitución. No hay más eventos de ese scan.
  `close`/EOF pueden terminar sin eventos terminales pendientes.

Si B sustituye A, se emite inmediatamente `completed` para A con estado `aborted`
y `reason:"superseded"`, seguido del ack de B. B espera en `queued` si A sigue en
una syscall; solo un escaneo (pool de 1–4 workers) visita disco a la vez. C puede
sustituir B sin iniciar otro pool. Resultados tardíos de A/B se descartan. Cancelar una solicitud en
espera la aborta inmediatamente. Cancelar una activa responde `cancelling`; el
terminal posterior es `aborted,reason:"cancelled"`, aun si el worker terminó pero
el resultado aún no fue publicado. Cancelar un scan ya terminal conserva su
estado/snapshot. `close` no espera al worker.

Contadores: `directories_seen` incluye raíz y nodos de directorio excluidos;
`files_seen` cuenta entradas no directorio procesadas, incluidos enlaces y
objetos especiales; `allocated_bytes_processed` son bytes asignados contabilizados
hasta ese momento, deduplicados. No son bytes leídos ni una estimación del total.
Se consultan mediante atomics y pueden corresponder a instantes ligeramente
diferentes. `elapsed_ms` de status incluye la espera y queda congelado al terminar;
el del evento de éxito mide el coordinador y su pool, incluida finalización.
Los workers publican archivos/bytes por lotes de 256 o al terminar un directorio:
pueden quedar hasta 255 entradas por worker pendientes de reflejarse. Los
hardlinks usan dedup global y sus cambios de propietario pueden ajustar bytes.
No mostrar porcentaje.

## Ejemplo completo

Los valores `S`, identidades y tamaños son ilustrativos. El cliente toma el
`scan_id` real del ack; no lo construye.

```json
{"id":"scan-1","action":"scan","root":"/ruta/elegida"}
{"protocol":1,"type":"response","id":"scan-1","action":"scan","ok":true,"data":{"scan_id":"S","request_id":"scan-1","state":"scanning","elapsed_ms":0,"progress":{"directories_seen":0,"files_seen":0,"allocated_bytes_processed":0}}}
{"protocol":1,"type":"event","event":"progress","request_id":"scan-1","scan_id":"S","seq":1,"state":"scanning","data":{"scan_id":"S","request_id":"scan-1","state":"scanning","elapsed_ms":250,"progress":{"directories_seen":20,"files_seen":100,"allocated_bytes_processed":409600}}}
{"id":"status-1","action":"status"}
{"protocol":1,"type":"response","id":"status-1","action":"status","ok":true,"data":{"scan_id":"S","request_id":"scan-1","state":"scanning","elapsed_ms":260,"progress":{"directories_seen":20,"files_seen":110,"allocated_bytes_processed":450560}}}
{"protocol":1,"type":"event","event":"completed","request_id":"scan-1","scan_id":"S","seq":2,"state":"finished","data":{"total_bytes":524288,"issue_count":0,"directories_retained":21,"elapsed_ms":300,"excluded_count":0,"identity":{"dev":"2049","ino":"123","mount_id":"45"}}}
{"id":"browse-1","action":"browse","scan_id":"S","path":"","offset":0,"limit":64,"sort":"size_desc"}
```

La respuesta de browse tiene este contenido en `data` (filas abreviadas aquí;
los nodos de directorio incluyen los mismos campos que `node`):

```json
{
  "scan_id":"S",
  "node":{
    "node_id":0,"name":"","name_hex":"","type":"directory",
    "allocated_bytes":524288,"own_bytes":4096,"direct_files_bytes":8192,
    "direct_entries":3,"excluded_entries":0,"child_directories":2,
    "issue_count":0,"subtree_issue_count":0,"complete":true,
    "issues":[],"issue_samples_truncated":false,"exclusion":null
  },
  "root_hex":"2f727574612f656c6567696461",
  "path":"","path_hex":"",
  "breadcrumbs":[{"node_id":0,"name":"/ruta/elegida","name_hex":""}],
  "children":[
    {"node_id":1,"name":"big","name_hex":"626967","type":"directory","allocated_bytes":409600},
    {"node_id":2,"name":"small","name_hex":"736d616c6c","type":"directory","allocated_bytes":102400},
    {"type":"files","name":"Direct entries","allocated_bytes":8192,"entries":3}
  ],
  "offset":0,"limit":64,"total_children":3,"next_offset":null,
  "sort":"size_desc","file_detail":"aggregated","directory_detail":"retained"
}
```

`allocated_bytes = own_bytes + direct_files_bytes + suma de hijos directorio`.
`direct_entries` cuenta todas las entradas no directorio incluidas, incluso los
hardlinks cuyo tamaño se atribuyó a otro nodo. `excluded_entries` cuenta montajes
de archivos omitidos, sin sus bytes. La fila `files` no tiene `node_id` y no es
navegable; la UI debe traducir su etiqueta según `type`, no tratarla como ruta.
Todos los nombres individuales de archivos están agregados intencionalmente.

`name`/`path` son texto de presentación con reemplazo U+FFFD si hay bytes no
UTF-8; no usarlos para volver a resolver rutas. `name_hex`/`path_hex`/`root_hex`
preservan los bytes exactos. Breadcrumbs usan `node_id`; el de raíz usa su ruta
como texto y nombre relativo vacío. JSON escapa saltos de línea/control/comillas.
El renderizado de nombres debe ser texto plano, nunca RichText interpretado.

`excluded_count` del evento terminado suma las exclusiones intencionales de
directorios y entradas de todo el snapshot; no incluye bytes de esas rutas.
`issue_count` es local, `subtree_issue_count` agrega descendientes. Cada issue
incluye `code`, `errno` numérico o null y `name_hex` relativo opcional. Hasta 16
muestras locales, sin limitar el conteo real. `complete:false` indica un issue
local/descendiente o que el nodo es una exclusión. `exclusion:"mount_boundary"`
indica exclusión intencional, cero bytes y cero hijos leídos.
`exclusion:"protected_path"` identifica `/root` omitido al analizar `/`.
`complete` sigue siendo un criterio conservador de ausencia de cualquier issue;
no equivale a `coverage_incomplete`. Ver la distinción siguiente. La etiqueta
`directory_detail:"retained"` significa que todos los directorios **descubiertos**
están almacenados; los issues/exclusiones explican lo no visitado.

```json
{"id":"browse-2","action":"browse","scan_id":"S","node_id":1,"offset":64,"limit":64}
{"id":"cancel-1","action":"cancel","scan_id":"S"}
{"id":"close-1","action":"close"}
```

Errores comunes de solicitud: `invalid_request`, `invalid_id`, `unknown_action`,
`root_required`, `invalid_root`, `parent_component_forbidden`, `invalid_hex`,
`ambiguous_path`, `invalid_workers`, `no_scan`, `stale_scan`, `snapshot_not_ready`, `node_not_found`,
`invalid_limit`, `invalid_sort`, `frame_too_large`, `response_too_large`.
Fallos de worker incluyen `root_open_failed`, `root_stat_failed`,
`root_read_failed`, `mount_identity_unavailable`, `mountinfo_unavailable`,
`mounts_changed`, `root_changed`, `worker_failed`; llevan `errno` cuando existe.
Issues de carpetas incluyen `stat_entry`, `open_directory`, `read_directory`,
`directory_replaced`, `directory_changed`, `directory_metadata_changed`,
`directory_removed`, `directory_stat`,
`mount_identity_unavailable` y `depth_limit`.

## Integración instalada con Quickshell

`src/quickshell/scripts/storage/control.py` adapta JSONL al servicio Storage.qml.
Conserva IDs opacos y pide páginas por `node_id`, correlaciona respuestas, valida
el token de mount antes de navegar y cancela con el `scan_id` de ese proceso.
El bridge mantiene como máximo tres procesos con snapshots terminados y un
candidato; solo uno analiza disco. Eso permite conservar el anterior durante
reanálisis sin cambiar la semántica de sustitución de cada motor individual.
Los estados `finished*` se presentan como `complete`/`complete-with-warnings`;
fallos/abortos no publican ni cachean un árbol. Cerrar stdin termina el proceso.
Inventario Python y el contrato pequeño bridge/QML no son el protocolo Rust.
Ver [Storage](../../docs/features/storage.md) para resolución, empaquetado y tests.


Para integrar esta fase en el hilo `storage`, propagar los nuevos contadores y
booleans al bridge/UI y dejar de interpretar `issue_count` como errores de lectura.
Mantener la correlación por `id`/`scan_id`, los campos de chart/query/others y las
páginas existentes. Se conserva el protocolo 1; requests antiguos siguen siendo
válidos y solo cambia el default de concurrencia. No se cambió código Python/QML
en esta fase; cualquier etiqueta del bridge que todavía agrupe todos los issues
necesita esa adaptación posterior. La caché del motor es el snapshot inmutable y
su ranking; nunca se reutilizan tamaños de un scan anterior para un nuevo scan.
