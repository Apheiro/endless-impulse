# Storage

Settings → Sistema → **Storage** usa el motor nativo Rust `endless-storage`.
Python conserva exclusivamente inventario de dispositivos y adaptación de páginas
IPC; no escanea árboles ni usa ncdu. Se mantiene la barra por carpetas reales,
selección de dispositivos físicos/particiones/FUSE y navegador inferior.

## Flujo y contabilidad

El inventario lsblk/mountinfo/statvfs aparece sin esperar el análisis. No se
solicitan seriales ni WWN. Los dispositivos sin montar muestran capacidad de
bloque y nunca se escanean ni montan automáticamente. Seleccionar un volumen
montado inicia un solo análisis, con debounce de 180 ms. Una ruta avanzada debe
pertenecer al volumen autorizado; se rechazan symlinks y `/root`.

Durante el análisis se muestran carga indeterminada, entradas/directorios,
bytes asignados procesados y tiempo real. Los contadores no son una estimación
del total ni bytes leídos de contenido. Un fixture diminuto puede terminar antes
del primer evento de progreso (250 ms). Settings no recorre archivos en QML.

| Motor Rust | Estado de presentación | Resultado |
| --- | --- | --- |
| `queued`, `scanning`, `cancelling` | `running` | Progreso/cancelación; nunca publica el árbol en curso. |
| `finished` | `complete` | Snapshot nativo validado y navegación. |
| `finished-with-warnings` | `complete-with-warnings` | Carpetas medidas visibles, cobertura limitada y ramas marcadas. |
| `failed` | `error` | Código/errno sanitizados, reintento manual; sin árbol nuevo. |
| `aborted` | `cancelled` | No publica ni cachea el prefijo cancelado. |

Una actualización conserva el último resultado válido, incluidas sus advertencias,
marcado como anterior. Solo un nuevo éxito lo reemplaza. Cerrar la página o cambiar
selección cancela la generación activa con su `scan_id`; las respuestas tardías se
ignoran. No hay auto-retry después de fallo/cancelación. Reentrar sin caché puede
iniciar otro scan. Tras cerrar todo Settings no quedan snapshots de sesión.

La asignación analizada es `st_blocks * 512`, con hardlinks regulares deduplicados,
no el uso global de `df`. El resumen del volumen usa statvfs:

- `total = f_blocks × (f_frsize o f_bsize)`;
- `usado = total − f_bfree × unidad`;
- `disponible = f_bavail × unidad`;
- `reservado/no disponible = libre − disponible`.

La barra se segmenta con nombres de hijos directos. Hasta siete carpetas
prominentes se eligen por bytes y ancho real. «Otras carpetas» suma **todos** los
hijos pequeños, incluso los de otras páginas, nunca una diferencia con statvfs.
Los archivos/entradas directos y bloques propios del directorio son agregados
separados, sin navegación ficticia a archivos. Breadcrumbs y filas navegan con
`node_id` nativos; los nombres con bytes no UTF-8 se muestran con reemplazo, pero
su navegación no se resuelve usando ese texto.

La suma de segmentos medidos coincide con el nodo. Ordenar, filtrar, cambiar ancho
y paginar no escanean de nuevo ni cambian el denominador por el subconjunto
visible. Las páginas de UI tienen hasta 60 carpetas; el protocolo admite 128 y
puede reducirse a una fila para nombres extremos sin descartar el snapshot.

Con advertencias, la barra usa **solo la escala medida**. Se marca cobertura
limitada, issues por rama y detalle `code`/`errno` local en Avanzado. Los issues
incluyen cambios durante la visita, EACCES/EIO, fallos de metadatos y profundidad;
no son todos permisos ni un número de archivos perdidos. Se muestran hasta 16
muestras locales, manteniendo el conteo total. La diferencia con usado se informa
como cifra contable separada, nunca como archivos inaccesibles medidos o espacio
recuperable. Los tamaños de las ramas afectadas llevan `≈`.

En la raíz de un volumen sin issues y con suma medida menor o igual al usado,
la barra puede completar la capacidad con diferencia no atribuible, reservado y
disponible. Si la suma supera usado, se conserva la escala medida y se informa el
exceso. Metadatos del FS, exclusiones, archivos eliminados abiertos, compresión y
bloques compartidos pueden explicar diferencias; ninguna se diagnostica por mera
resta. No se ha verificado que el árbol real del usuario coincida con Filelight.

## Proceso, caché y límites

`runtime/storage/src/scan.rs` conserva todos los directorios descubiertos; agrega
los archivos directos y usa un solo worker. No hay export gigante, parser ncdu,
límite de 50k/250k directorios ni «Folder detail not retained». El detalle no leído
por permisos, montajes o profundidad conserva un motivo explícito.

`control.py` adapta el [protocolo](../../runtime/storage/PROTOCOL.md) a la página.
Cada proceso nativo posee un snapshot. El bridge conserva como máximo **tres
snapshots terminados** y un candidato durante reanálisis; solo el candidato
recorre disco. Los demás responden desde memoria. Al reemplazar/desalojar se cierra
su proceso. No se guarda un árbol de nombres en disco. La caché se valida contra
el token de mount antes de navegar; no detecta todas las modificaciones de datos
posteriores al scan. Refrescar/reanalizar es explícito.

No existe presupuesto fijo de memoria que convierta ramas en totales sin detalle.
La memoria es proporcional a directorios y hardlinks; tres árboles grandes pueden
consumir bastante RAM y no hay garantía contra OOM externo. Rust limita profundidad
a 128 y lo comunica como issue. No hay plazo máximo del análisis; QML detecta
15 segundos sin respuesta/progreso del worker y concede 3 segundos a cancelar
antes de cerrar el bridge. EOF cierra los procesos nativos aunque una syscall de
FUSE esté bloqueada. IPC pagina memoria, nunca vuelve a leer el filesystem.

Los frames nativos se limitan a 262144 bytes; un caso extremo de nombres/issues
puede producir `response_too_large` incluso con una sola fila. Se informa error,
sin inventar resultados ni compactar datos. Las respuestas se correlacionan por
ID; los snapshots tienen IDs opacos de sesión. El código de UI no exige flags
`exportComplete`/`exitCode` del motor anterior.

El motor no sigue symlinks ni cruza dispositivo/mount ID, incluidos bind mounts.
En `/` se excluyen `/proc`, `/sys`, `/dev` y `/root`; estas exclusiones intencionales
no son un fallo global. Cambios de mounts o identidad de raíz invalidan el scan.
No hay sudo, limpieza, cambio de permisos, desmontaje ni modificación de datos.

## Construcción, instalación y resolución

```bash
cargo build --offline --locked --release --manifest-path runtime/storage/Cargo.toml
```

El binario de este checkout queda en
`runtime/storage/target/release/endless-storage`. El modo fuente lo encuentra sin
instalar nada. La resolución es, en orden:

1. `DOTS_STORAGE_EXECUTABLE`, si se define (un override inválido falla explícitamente);
2. `runtime/storage/endless-storage` dentro del shell desplegado;
3. binario release del checkout;
4. `${XDG_DATA_HOME:-~/.local/share}/dots-hyperland/storage/endless-storage`;
5. `endless-storage` en PATH.

El instalador tradicional compila con Cargo.lock y copia el ejecutable al punto 4
antes de desplegar archivos, también en `setup install-files`. Arch declara `rust`
y Fedora `rust`/`cargo` como herramientas de build; ncdu dejó de ser dependencia
Storage. Esta integración no desinstala el ncdu que ya tenga el usuario.

Nix usa `rustPlatform.buildRustPackage`, Cargo.lock y una derivación separada;
inyecta la ruta absoluta mediante `DOTS_STORAGE_EXECUTABLE` y enlaza el binario
junto al QML instalado. `./dev settings` usa el mismo empaquetado y fuente QML del
checkout. El dev launcher usa referencia `path:` para incluir archivos nuevos sin
exigir staging/commit. No se compila automáticamente desde la página.

Si falta el binario, el inventario sigue funcionando y aparece un error de
instalación con indicación de reconstruir/reinstalar y actualizar dispositivos.
No se cambia silenciosamente a otro scanner. Tras reconstruir, **Refresh devices**
vuelve a comprobar su disponibilidad; no es necesario reiniciar Hyprland.

## Validación aislada

```bash
cargo test --offline --locked --manifest-path runtime/storage/Cargo.toml
cargo fmt --manifest-path runtime/storage/Cargo.toml --check
cargo clippy --offline --locked --manifest-path runtime/storage/Cargo.toml --all-targets -- -D warnings
python3 -m pytest tests/test_storage.py tests/test_storage_qml.py
python3 -m pytest tests/test_dependency_map.py tests/test_repository_layout.py tests/test_hardware_projection.py
python3 -m py_compile src/quickshell/scripts/storage/control.py src/quickshell/scripts/storage/inventory.py
nix-instantiate --parse packaging/nix/package.nix
bash -n dev installer/lib/package-installers.sh installer/commands/install/3.files.sh
git diff --check
```

Los tests Python y QML invocan **Rust real** únicamente sobre fixtures temporales:
`home` sintético, sparse, hardlinks, symlinks, nombres inválidos UTF-8, permisos,
cancelación, fallo/reanálisis, caché, paginado, búsqueda y «Otras carpetas» global.
QML carga la página y componentes nativos con inventario simulado y XDG aislado;
se cubren claro/oscuro, escala y ancho/estrecho. Solo se desactiva OpacityMask en
la copia temporal del botón por limitaciones del renderer software. Rust también
inyecta límites de mount y errores sin crear mounts ni modificar el sistema.

No se escanearon `/`, `/home`, ProtonDrive ni datos personales. No se reinició la
sesión ni se ejecutó instalación global. La suite Rust necesita permiso para el
socket Unix temporal del fixture. El benchmark sintético sigue ignorado por
defecto; no se promete velocidad/RSS equivalente a Filelight con 650 GiB reales.
El build completo Nix, despliegue Arch/Fedora y revisión del usuario en su sesión
quedan pendientes; el parseo Nix/Bash no sustituye esas pruebas.

Resultado de la integración: **18 pruebas Python Storage + 6 QML offscreen PASS**,
**10 regresiones PASS** (18 subtests adicionales), **15 tests Rust PASS**. El
benchmark Rust permanece ignorado explícitamente (1), no es un fallo de scan.
Build release, fmt, clippy sin warnings, py_compile, sintaxis QML/Qt6, Bash,
parseo Nix y `git diff --check` PASS. El helper tradicional se prueba copiando el
binario real únicamente a un XDG temporal; no se ejecuta setup sobre el host.
Los casos con bytes inválidos que tienen el mismo texto de presentación mantienen
IDs y claves de color distintos. Se revisaron capturas aisladas ancha/estrecha.
