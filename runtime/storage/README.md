# endless-storage

Motor Linux autónomo para Endless Impulse. Código original, sin código de
Filelight, Qt, QML, ncdu ni Python. Es el motor activo de Settings → Storage;
QML y el bridge Python consumen páginas sin exportar el árbol.
La licencia del repositorio se encuentra en [LICENSE](../../LICENSE).

## Compilar y ejecutar

Probado con Rust/Cargo 1.96.1. `Cargo.lock` fija las dependencias; requiere Linux
con `statx(STATX_MNT_ID)` (kernel 5.8 o posterior) y `/proc/self/mountinfo` legible.
No usa `sudo`, no instala paquetes y no modifica archivos del usuario.

```bash
cargo build --locked --release --manifest-path runtime/storage/Cargo.toml
runtime/storage/target/release/endless-storage
# Alternativa de desarrollo, conserva stdin/stdout del proceso:
runtime/storage/dev run
```

Solo tres dependencias directas: `libc` para descriptores y metadatos Linux,
`serde` y `serde_json` para el protocolo. Se compilaron usando la caché local con
`--offline --locked`; no se descargaron dependencias durante el desarrollo.
El script no altera Arch, Nix ni sus locks. Arch/Fedora compilan con Cargo en la fase de archivos del instalador y Nix
usa una derivación Rust independiente. No usar `cargo run` en la aplicación instalada: invocar el
binario ya compilado con ruta absoluta.

```bash
runtime/storage/dev check
# Equivalentes explícitos, también admiten --offline con la caché preparada:
cargo test --locked --manifest-path runtime/storage/Cargo.toml
cargo fmt --manifest-path runtime/storage/Cargo.toml --check
cargo clippy --locked --manifest-path runtime/storage/Cargo.toml --all-targets -- -D warnings
runtime/storage/dev bench
```

Las pruebas usan directorios temporales y metadatos de sus fixtures, nunca `/`
ni un home real. La prueba de sockets necesita poder crear un socket Unix bajo
el directorio temporal; un sandbox que prohíba `bind` puede rechazarla con EPERM.
La comparación de bloques requiere GNU `du` disponible. Montajes y permisos/EIO
se inyectan mediante `scan::Options`, sin montar ni cambiar permisos, incluso
si los tests se ejecutan como root. La inyección no está expuesta por IPC.

## Arquitectura

- `src/scan.rs`: DFS iterativo, `readdir`, `fstatat(AT_SYMLINK_NOFOLLOW)`,
  `openat(O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC)` y `statx` por directorio. Cada
  componente de la raíz se abre sin seguir symlinks. No se lee contenido de
  archivos. La única lectura de contenido ajena a los fixtures es la tabla de
  montajes del kernel.
- `src/ipc.rs`: dispatcher dueño del snapshot y de stdout, lector stdin con cola
  acotada y un único coordinador de escaneo con pool limitado a 1–4 workers.
  No crea un hilo por directorio. Sustituir A por B cancela el pool de A y espera
  su salida antes de iniciar B; solicitudes posteriores ocupan una sola espera.
- `src/main.rs`: ejecutable; diagnósticos sanitizados exclusivamente en stderr.
- `tests/acceptance.rs`: conteo, navegación sin reescaneo, protocolo, carreras,
  errores y benchmark sintético. `dev` facilita ejecutar y comprobar el crate.

Se suman `st_blocks * 512`, incluidos los bloques propios de cada directorio y
los de archivos directos, symlinks y otros tipos. No se usa tamaño aparente.
Los archivos sparse y vacíos conservan su asignación real. Solo los archivos
**regulares con nlink > 1** entran en la tabla `(dev, ino)` de deduplicación.
El ganador es la menor ruta relativa por orden de bytes, independientemente del
orden de `readdir`. Los directorios nunca se deduplican por `nlink`. El total
coincide con `du -sx -B1` para fixtures comparables, sin montajes excluidos ni
hardlinks múltiples a symlinks/otros tipos. La atribución por carpeta puede
ser distinta de `du`, cuyo orden de visita decide dónde carga un hardlink.

Todos los directorios descubiertos se conservan. Los archivos no se almacenan
individualmente: una fila sintética `files` agrupa las entradas directas, aun
cuando su suma sea cero. La suma de un nodo incluye sus bloques propios, esa
fila y sus subdirectorios. No existe presupuesto de bytes que convierta una
carpeta grande en “detail not retained”. Los directorios excluidos o no leídos
conservan su nodo y el motivo explícito; no se presentan como vacíos completos.

## Seguridad, montajes y consistencia

Nunca se siguen symlinks, tampoco dentro de la ruta raíz. La raíz debe ser
absoluta y no contener `..`. `browse` consulta únicamente memoria, admite rutas
relativas y rechaza `..` y rutas absolutas; no puede abrir nuevas rutas.

Un hijo con otro `st_dev`, otro mount ID, o declarado como mountpoint en
`/proc/self/mountinfo` se excluye, incluidos bind mounts del mismo dispositivo y
montajes de archivos. En `/` también se excluyen intencionalmente `/proc`, `/sys`, `/dev`
y `/root` (ruta protegida). Una raíz solicitada explícitamente puede ser un mountpoint o pseudoFS;
se analiza ese montaje y se siguen excluyendo sus submontajes. Las exclusiones
intencionales no convierten el resultado en advertencia.

Se compara identidad `(dev, ino)` antes/después de abrir directorios. Se comprueba
el mount ID al abrir cada directorio y la identidad de la raíz al finalizar. Si
cambia la tabla de montajes entre inicio y fin se falla con `mounts_changed`, sin
publicar un snapshot mezclado. Cambios de mtime/ctime de un directorio durante su
visita generan observaciones de inestabilidad, separadas de los fallos de
cobertura. EACCES, EIO, ENOENT y directorios eliminados/reemplazados generan
incidencias de cobertura propagadas hacia sus ancestros. Ver la clasificación
y su incertidumbre explícita en [PROTOCOL.md](PROTOCOL.md#clasificación-de-incidentes).
Los eventos globales no incluyen rutas ni muestras de error; solo `browse`
solicitado muestra nombres y detalles. Stderr nunca imprime payloads ni rutas.

## Memoria y límites conocidos

Memoria O(D + H × L + workers × profundidad), donde D son directorios, H archivos regulares
con múltiples enlaces y L longitud de su ruta. No hay lista de los millones de
archivos ordinarios ni exportación JSON del árbol. Cada nodo tiene nombre crudo,
últimos campos de suma, índices de hijos y hasta 16 muestras de issues; el conteo
de issues es completo aunque las muestras se limiten. `issue_samples_truncated`
lo indica. `browse` usa temporalmente O(hijos directos) índices para ordenar y
serializa solo una página y hasta siete segmentos prominentes más el agregado
de hijos pequeños. Al finalizar, el vector de hijos existente se ordena por
tamaño/nombre una sola vez: cachea el ranking sin duplicar el índice del árbol.
Browse por tamaño y los segmentos reutilizan ese orden; el total de «Otros» se
obtiene por resta de sumas ya verificadas. El filtro y el paginado no alteran los
totales. La caché dura lo que el snapshot inmutable, sin persistencia ni reutilizar
metadatos de un escaneo anterior cuya validez no pueda garantizarse.

- Profundidad máxima predeterminada: 128. El nodo que excede el límite conserva
  sus bloques propios y `depth_limit`, sin inventar el tamaño de sus hijos.
  Este límite protege descriptores y rutas; es una advertencia visible. La API
  Rust permite ajustarlo, el protocolo v1 deliberadamente no.
- Memoria proporcional a todos los directorios y hardlinks, sin máximo global
  de nodos. Millones de archivos en pocas carpetas no incrementan el árbol;
  millones de carpetas o hardlinks sí consumen RAM. No hay spill a disco ni
  recuperación garantizada de OOM. Este diseño no ha sido medido en un disco real
  con millones de directorios.
- Pool limitado, default 2 y override 1–4; no hay detección automática fiable del
  dispositivo físico detrás de binds/LVM/RAID. Para HDD o presión de I/O, usar 1.
  Los benchmarks actuales son de tmpfs y no predicen comportamiento en HDD/NVMe.
  No se afirma rendimiento comparable/superior a Filelight.
- No hay snapshot atómico del filesystem. Archivos creados, borrados, movidos o
  cambiados durante el escaneo pueden producir una vista temporal; comprobar
  mtime/ctime de directorios no detecta todas las modificaciones de archivos.
  Cambios de montaje que se reviertan entre comprobaciones tampoco constituyen
  una transacción del kernel. El snapshot publicado es inmutable y no se valida
  de nuevo al navegar: refleja ese escaneo, aunque después se desconecte el disco.
- La cancelación se comprueba entre entradas y al plegar sumas. Una syscall
  bloqueada por un volumen remoto/desconectado puede retrasar cancelación y el
  comienzo del siguiente escaneo; `status` y `close` continúan por el dispatcher.
- El cliente debe drenar stdout. Un pipe lleno ejerce backpressure sobre el
  dispatcher; no hay una cola ilimitada de eventos. EOF/close termina el proceso
  sin esperar una syscall bloqueada. No queda snapshot parcial publicado.
- Se contabiliza asignación por inode, no extents compartidos/reflinks,
  compresión, deduplicación del FS, cuotas, espacio reservado o uso global del
  volumen. `du` puede tener políticas distintas en ciertos FS/objetos especiales.
- JSON representa contadores como enteros u64; JavaScript solo mantiene exactitud
  entera hasta `2^53-1` (aprox. 8 PiB en bytes). Identidades de volumen e inode y
  `scan_id` se transmiten como strings para evitar pérdida de identidad.

Ver [PROTOCOL.md](PROTOCOL.md) para el contrato IPC v1 y la integración con Quickshell; [Storage](../../docs/features/storage.md)
documenta resolución de binario, caché y pruebas de la página.

## Concurrencia y optimizaciones

Opciones aditivas del protocolo: `{id:"s",action:"scan",root:"/ruta",workers:1}`
(el ejemplo es un objeto JS; por stdin debe ser JSON válido). `workers` acepta
1–4, default 2. El ejecutable admite `ENDLESS_STORAGE_WORKERS=1` como default del
proceso; el campo de la solicitud tiene prioridad. Un valor de entorno inválido
se ignora; un campo IPC inválido responde `invalid_workers` sin cancelar el scan
actual. La API Rust ofrece `Options.workers`; no consulta variables de entorno.

Los helpers se crean de forma perezosa al descubrir un subárbol independiente,
tras observar 16 directorios o procesar 256 archivos. Un árbol pequeño o una sola
carpeta de archivos sin subárboles permanece secuencial. No es una detección de
SSD ni una garantía de acelerar cualquier árbol. El usuario puede fijar 1 para
HDD y probar 2/4 en SSD/NVMe cuando corresponda, midiendo después.

La cola permite como máximo `2 × workers` tareas con descriptores ya abiertos y
validados; si se llena, el worker desciende por DFS local. Los descriptores quedan
acotados por `workers × (max_depth + 1) + 2 × workers`, más los de raíz/IPC. Cada
stream de directorio posee su descriptor, sin dup/fcntl redundante. Un statx
valida `(dev,ino,mount ID)` juntos al abrir; se conserva fstat al finalizar,
la tabla de montajes y la identidad final de raíz. No se elimina seguridad para
reducir syscalls. El pool no divide un archivo ni sigue un symlink.

Cada worker acumula sus archivos/bytes sin bloquear el árbol por archivo.
Publica contadores cada 256 archivos o al terminar una carpeta; el progreso
puede retrasarse hasta 255 entradas por worker. La reserva/publicación de nodos
usa mutex por directorio. Solo hardlinks regulares usan el mutex global de
inodes; se elige propietario por ruta relativa cruda, y la asignación de bytes
se aplica una vez cuando han terminado todos los workers. La atribución no
depende de qué worker llegó primero. Cancelación/panic descartan el árbol parcial;
se comprueba cancelación también durante dedup y plegado, antes de devolverlo.

Por inspección, se quitaron las rutas/CString duplicadas de archivos ordinarios,
el fstatat redundante antes de statx y el dup/fcntl por directorio, y se agruparon
los atomics por archivo. No hay un perfil con strace: esos ahorros son cambios
identificables en el código, no contadores de syscalls medidos.

## Verificación y benchmark

Verificación del agente, separada de las pruebas del usuario y del escritorio:
26 tests PASS (25 de aceptación y uno unitario), 0 FAIL; un benchmark de test se
omite por defecto y se ejecuta aparte. `cargo fmt --check`, Clippy con
`--all-targets -- -D warnings` y build release PASS. Incluye comparación con GNU
`du`, workers 1/2/4 con hardlinks cruzados y mismo árbol por ruta, sparse,
symlinks, límites de montajes inyectados, errores de open/read/stat/mount ID,
clasificación de cambios, cancelación en varias fases, panic del worker,
IPC activo durante bloqueo/sustitución y páginas estables de «Otros»/no UTF-8.
La suite necesita permitir bind del socket Unix temporal cuando el sandbox lo
bloquee; no usa sudo, chmod, montajes ni datos reales del usuario.

Benchmark reproducible en [examples/fixture_bench.rs](examples/fixture_bench.rs):
crea y limpia únicamente fixtures temporales. Compara los workers nuevos entre
sí y opcionalmente un binario baseline; el segundo argumento **es un ejecutable**,
no una raíz para analizar.

```bash
cargo build --offline --locked --release --manifest-path runtime/storage/Cargo.toml --bins --examples
cargo run --offline --locked --release --manifest-path runtime/storage/Cargo.toml --example fixture_bench -- runtime/storage/target/release/endless-storage
# Agregar como último argumento la ruta absoluta del ejecutable baseline preservado.
```

Condiciones de la medición de esta fase: Rust 1.96.1, build release, `/tmp` sobre
**tmpfs**, 12 CPUs lógicas visibles, caché caliente, archivos vacíos. Nueve rondas
por configuración tras un warmup, orden de configuraciones rotativo y escaneos
secuenciales entre configuraciones. Medida: `completed.data.elapsed_ms` del
coordinador (incluye pool/finalización; excluye creación del fixture, arranque del
proceso y espera de polling IPC). RSS: VmHWM del proceso propio, después de diez
escaneos, incluye runtime/stacks/allocator. Son muestras de este entorno, no
mediciones de disco ni predicciones para HDD/NVMe.

| Fixture | Baseline secuencial | Nuevo 1 | Nuevo 2 | Nuevo 4 |
| --- | ---: | ---: | ---: | ---: |
| 24 archivos / 10 directorios | <1 ms | <1 ms | <1 ms | <1 ms |
| 51 200 archivos / 161 directorios | 80 ms | 69 ms | 38 ms | 21 ms |
| 6 144 archivos / 1 569 directorios | 27 ms | 24 ms | 13 ms | 7 ms |

Son medianas con resolución de milisegundos; los ceros del fixture pequeño no
significan duración cero. Rango min–max del caso de 51 200 archivos: baseline
72–84 ms; nuevo 1: 67–71; nuevo 2: 37–40; nuevo 4: 20–23. RSS máximo en ese caso:
baseline 3 332 KiB; nuevo 1/2/4: 3 424/3 604/3 764 KiB, reteniendo **161 nodos y
cero inodes de hardlinks**, nunca 51 200 registros. En el caso con más directorios:
baseline 4 968 KiB; nuevo 1/2/4: 4 896/6 068/7 560 KiB. El árbol pequeño creó un
solo worker con cualquier límite; los otros crearon 1/2/4 y la cola no superó
1/4/8 tareas respectivamente.

Baseline: ejecutable anterior a esta fase, preservado temporalmente antes de
editar; SHA-256 `416c0eb977945e66d50f765cd676cb94e1cbaf2b73c4ee729e7c1bf456a5702c`,
fuente scan.rs inicial `c1851c4a9d1bfa8a704481f8496ed575f043fd274bf1d25dac3468b59f542f9d`.
Los dos motores verificaron iguales totales y cantidad de directorios en todos
los fixtures. No se ha medido Filelight ni escaneado `/` o `/home` reales.

## Integración con Settings

El launcher resuelve un binario ya compilado, sin fallback a ncdu. Navegar,
filtrar, cambiar ancho y consultar «Otras carpetas» usan browse del snapshot,
sin reescaneo. Se retiene el anterior durante una actualización hasta validar
el candidato; advertencias de lectura permiten usar los bytes observados con
cobertura limitada. El motor sigue conservando todos los directorios descubiertos,
sin presupuesto de detalle que convierta `/home` en un agregado sin navegación.

La prueba adicional de agregación verifica 171 hijos, páginas de 60, filtro,
orden y «Otros» sobre todos los hijos. La integración se prueba también con
Rust real + Python/QML offscreen sobre fixtures temporales. No se ha medido el
disco real del usuario, ni se ha instalado o reiniciado su sesión para probarla.

## Entrega al hilo `storage`

El protocolo sigue siendo v1, con campos aditivos y la corrección documentada de
`finished` para cambios sin fallos de cobertura. El bridge debe propagar
`unstable_entries`, `unreadable_count`, `excluded_count`, `changes_observed`,
`coverage_incomplete` y `coverage_uncertain`, en vez de llamar «no se pudo leer»
a todo `issue_count`. Conservar la opción de navegar ramas cambiantes, mostrar
«cambios observados» y distinguir incertidumbre de una omisión real. `node.complete`
conserva su criterio conservador anterior; para explicar lectura usar los nuevos
campos. Ver el delta exacto y ejemplos en PROTOCOL.md. No se cambió Python/QML,
installer, paquetes ni otras features en esta fase. La selección UI de workers,
la caché multi-volumen del bridge y la validación del escritorio quedan para el
hilo `storage`, después de esta entrega secuencial.
