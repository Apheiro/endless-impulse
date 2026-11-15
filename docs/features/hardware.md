# Administrador nativo de hardware — V1

La página **Settings → Sistema → Hardware** explora componentes físicos y sus
interfaces. No sustituye las páginas de sonido, red, Bluetooth, monitores o entrada.
Esta entrega es de inventario y administración de **borradores propios**; no instala
reglas ni realiza operaciones sobre hardware.

## Archivos y arquitectura

| Archivo | Responsabilidad |
| --- | --- |
| `src/quickshell/modules/settings/HardwareConfig.qml` | Marco adaptable y navegación principal |
| `src/quickshell/modules/settings/hardware/*.qml` | Inventario, inspector, borradores, tablas y secciones plegables |
| `src/quickshell/modules/settings/SettingsCatalog.qml` | Registro en Sistema y búsqueda de la página |
| `src/quickshell/services/Hardware.qml` | Procesos asíncronos, selección, cola acotada, timeout y monitor de eventos |
| `src/quickshell/scripts/hardware/inventory.py` | Descubrimiento sysfs/udev y detalle de solo lectura |
| `src/quickshell/scripts/hardware/projection.py` | Agrupación física, paquetes CPU, categorías, relaciones y búsqueda |
| `src/quickshell/scripts/hardware/rules.py` | Validación, renderizado de reglas y almacenamiento exclusivo de borradores |
| `src/quickshell/scripts/hardware/control.py` | CLI JSON con operaciones explícitas y errores estables |
| `tests/test_hardware.py` | Fixtures sysfs, parsing, privacidad, validación, CRUD, fallos, CLI y lectura real del host |
| `tests/test_hardware_projection.py` | Fixtures de CPU, GPU, Bluetooth, hubs, teclados idénticos y universo de 1.500 nodos |
| `tests/test_hardware_qml.py` | Página/primitivas reales y backend real con estado temporal, navegación y sintaxis Qt 6 |
| `src/quickshell/translations/es_MX.json` | Textos de la función y errores en español |

Solo se usa la biblioteca estándar de Python. No se agregan paquetes ni se
actualizan locks. `udevadm` aporta propiedades y eventos; sin él permanece sysfs
y se informa inventario parcial. `getfacl` es opcional para ACL. `lsusb` y `lsblk`
se detectan como herramientas disponibles, pero V1 no depende de sus salidas.

## Organización visual y navegación

Hay dos espacios: **Dispositivos** y **Reglas udev (borradores)**. Ya no existe
una pestaña paralela de drivers con el mismo árbol. El driver y el kernel se
inspeccionan desde la ficha del dispositivo, con acceso a su padre asociado.

La página usa el ancho real que recibe del Loader de Settings, sin el límite
anterior de 880 px. Desde 850 px de contenido (ajustados al tamaño de fuente),
reserva aproximadamente 36% al inventario y 64% al inspector, con separación.
Son paneles adyacentes; el detalle nunca se coloca debajo de la lista en escritorio.
Por debajo del umbral se muestra inventario **o** detalle con un botón Volver;
se conservan categoría, búsqueda, expansión y contexto de componente. No se
agrega otra sidebar global ni un scroll exterior que contenga ambos paneles.

La portada muestra tarjetas de categorías con conteos reales de entidades:
gráficos, procesadores, almacenamiento, red física, Bluetooth, USB/hubs,
conectados/HID, audio y, bajo demanda, otros y virtuales. Un teclado USB reúne
sus interfaces, una GPU PCI reúne DRM y una CPU reúne las CPU lógicas por paquete,
con cantidad de núcleos solo cuando sysfs proporciona core IDs. Dos unidades
idénticas en puertos diferentes siguen siendo dos componentes.

«Componente» significa una entidad principal identificable (paquete CPU, función
PCI, unidad, adaptador o dispositivo conectado), no un recuento de todos los chips
de una placa. Los controladores PCI y sus unidades de almacenamiento pueden ser
entidades relacionadas diferentes. Los contadores de **componentes** y **nodos
técnicos** siempre se distinguen. Los nodos intermedios sin identidad de hardware
no inflan las categorías principales. La lectura del host durante el rediseño
produjo 1.301 nodos técnicos, 57 entidades no virtuales (34 en Otros) y 8 virtuales;
son valores de esa lectura, no constantes del producto.

**Conexiones** muestra la topología de componentes con las ramas contraídas.
**Avanzado: nodos técnicos (sysfs)** conserva el grafo exhaustivo, también
contraído. Buscar devuelve coincidencias directas con breadcrumb: en modo normal
se buscan entidades y sus interfaces, sin desplegar todos sus antecesores. Ver
conexión revela únicamente la ruta del componente sin cambiar la interfaz elegida.
Las ramas tienen botón y navegación con flechas derecha/izquierda.

Los índices de nodos, componentes e hijos se construyen una vez por snapshot.
Las filas usan ListView virtualizado; la portada usa GridView de diez categorías.
Solo uno de esos viewports está activo. Las listas empiezan con un presupuesto
de 60 filas; Mostrar más añade 60 hasta 600 por página, y Resultados siguientes /
anteriores permite acceder al resto sin necesitar conocer una ruta exacta.
No se instancian todos los nodos del host como widgets.

El inspector usa tarjetas y tablas de pares clave/valor, con dos grupos de datos
rápidos en paralelo cuando caben. Conexión/interfaces, controlador/kernel,
acceso/permisos y propiedades técnicas se abren por separado. Los cuerpos se
cargan al expandirlos. Interfaces se presentan de 12 en 12 y propiedades de 24
en 24, conservando el acceso al resto. La ficha mantiene el componente físico
al navegar interfaces y ofrece volver al conjunto. Las propiedades udev y
rutas técnicas no ocupan la portada. Una desconexión informa la ausencia y
conserva el identificador seleccionado para dar contexto.

## Inventario y ejecución

Cada lectura enumera enlaces de `/sys/bus/*/devices` y `/sys/class/*`, combina una
única exportación de udev y conserva la ascendencia bajo `/sys/devices`.
`inventory.py` devuelve el grafo completo y `projection.py` deriva la proyección
física por ascendencia, nunca uniendo por vendor/product. La clasificación PCI
interpreta códigos hexadecimales con o sin ceros iniciales. No se usan índices
`/dev/hidrawN` como identidad persistente: las rutas describen la topología actual
y pueden cambiar al mover un dispositivo de puerto.

La ficha lee bajo demanda driver, módulo, parámetros consultables, modalias,
atributos, nodos `/dev`, owner/grupo, modo y ACL. Firmware y alimentación solo
aparecen cuando sysfs los expone. Ausencia no equivale a una falla. Bluetooth
cubre adaptadores y vínculos publicados en sysfs, no el inventario remoto guardado
por BlueZ. No se leen registros del kernel ni se infiere salud del hardware.

No se leen archivos `serial`. Se filtran propiedades de series, WWN, UUID,
direcciones/UNIQ, DEVLINKS y PHYS. Las rutas sysfs reales siguen disponibles para
diagnóstico; este no es un informe anonimizado. No se exporta información a terceros.

Mientras la página está visible, `udevadm monitor --udev` solicita refrescos con
coalescencia de 750 ms desde el primer evento. Hay un solo worker y como máximo
una actualización pendiente. No hay sondeo periódico. Ocultar Settings o salir
de la página detiene el monitor. Las herramientas tienen plazo de 8 s y el worker
de 20 s. Tras error se pausa la actualización automática hasta reintento explícito.
Si el sandbox impide suscribirse al monitor, la UI informa que queda el refresco manual.

## Reglas propias: borradores exclusivamente

Desde Acceso y permisos de una interfaz compatible, **Preparar borrador de acceso** copia
el subsistema y los IDs exactos del mismo antecesor USB. El editor permite
`hidraw`, `input` (event), `ttyUSB`/`ttyACM` y nodos USB. No admite reglas generales
para discos, GPUs, red u otros subsistemas en V1.

El renderizador solo acepta SUBSYSTEM, KERNEL y ambos IDs vendor/product
hexadecimales exactos. Usa ATTRS para descendientes y ATTR para el dispositivo
USB mismo: ambos IDs deben corresponder al mismo nodo. Los patrones KERNEL
permitidos tienen estructura restringida; `*` global, comillas, escapes, saltos
de línea, comandos y claves adicionales son rechazados. Las únicas acciones
son `TAG+="uaccess"`, `MODE="0600"`/`"0660"` y GROUP de nombre válido y existente.
No se admite 0666, RUN, PROGRAM, shell, rutas de destino ni contenido libre.
El identificador solo admite minúsculas ASCII, dígitos y guiones (1–48 caracteres).
El único nombre de archivo generado es `70-endless-impulse-<id>.rules`.

El editor conserva el dispositivo de origen y ofrece Volver al dispositivo. Cambiar de pestaña no destruye el formulario. La vista previa muestra contenido udev real validado. **Confirmar y guardar solo
el borrador** actualiza metadatos propios de usuario; no crea ese archivo rules.
La descripción no se interpola en el contenido. Cambiar el identificador crea
otro borrador. Habilitar/deshabilitar solo modifica el plan de borradores:
siempre se muestra **sin instalar / instalación privilegiada pendiente**.
No hay botón de instalación ficticio ni invocación sudo/pkexec.

Las coincidencias incluyen todas las unidades del mismo vendor/product y clase
de interfaz seleccionada. `hidraw*` evita depender de su número cambiante, pero
puede incluir varias interfaces HID del producto. Una condición KERNEL exacta
puede dejar de coincidir al reconectar. El alcance se explica antes de guardar.
`uaccess` concede acceso a la sesión local activa; el acceso WebHID por sitio del
navegador se autoriza por separado. Otras reglas pueden solaparse o sobrescribir
resultados. Esta versión no lee, analiza, importa, adopta ni modifica reglas
externas, incluidas las reglas preexistentes del usuario.

Los únicos archivos persistentes propios son:

- `$XDG_STATE_HOME/endless-Impulse/hardware/drafts.json`: versión de esquema y reglas.
- `previous.json` en ese mismo directorio: colección anterior recuperable.
- `.lock` y temporales propios durante escrituras.

Se usan bloqueo entre procesos, directorio nuevo 0700, archivos nuevos 0600,
rechazo de enlaces simbólicos/archivos no regulares, límites de tamaño/cantidad,
reemplazo atómico, fsync y lectura posterior para comprobar el resultado.
Se conserva la copia previa antes de cada mutación; **Restaurar colección
anterior** intercambia las colecciones. No hay reintento automático de escrituras.
Los archivos inválidos no se sobrescriben. Estas protecciones son para estado de
usuario; este código no es un helper privilegiado y no debe reutilizarse como tal.

## Límites y siguiente etapa

No están disponibles bind/unbind, modprobe, reset, escrituras sysfs, cambios de
ACL, instalación de reglas, recarga/trigger de udev ni cambios de servicios. No se
reinicia ningún proceso de la sesión ni se altera la configuración instalada.

Una instalación futura requiere un helper **separado y empaquetado** con contrato
cerrado: recibir únicamente objetos validados, autenticar al sujeto correcto
mediante Polkit del sistema, reconstruir el contenido sin confiar en previews,
limitar nombres propios y directorio destino, usar descriptores de directorio y
O_NOFOLLOW, impedir adopción de archivos ajenos, verificar pertenencia por metadata,
conservar backup y transacción de rollback, confirmar la revisión exacta, realizar
verificación posterior y reportar divergencias. Ni rutas ni comandos libres deben
cruzar ese límite. La política Polkit, el empaquetado y la recuperación frente a
fallos deben probarse antes de habilitar instalación. Una instalación no debe
implicar por defecto reconfigurar todos los dispositivos del host.

Extensiones futuras separadas: fwupd (inventario/actualización con su autorización),
bolt (Thunderbolt), UDisks2 (datos de almacenamiento), USBGuard (políticas de
conexión) y sensores. Cada proveedor deberá declarar disponibilidad, campos,
errores y operaciones reales; no se simulan estas capacidades en V1.

## Verificación de esta entrega

Ejecutar desde el checkout, sin instalar nada:

```bash
python3 -m unittest discover -s tests -p 'test_hardware*.py' -v
python3 src/quickshell/scripts/hardware/control.py --request '{"action":"snapshot"}'
```

El segundo comando imprime JSON real del host y no escribe estado. La suite usa
estado temporal para CRUD y Qt offscreen; no carga la configuración personal.
`udevadm verify --root=<temporal>` verifica solo los archivos generados en el árbol
temporal, sin consultar reglas del sistema. La prueba de lectura real consulta
muestras de las categorías presentes, además del inventario completo.

| Comprobación del agente | Resultado |
| --- | --- |
| Fixtures sysfs, árbol, agrupación de interfaces, bound/unbound y módulo | PASS |
| Parsing udev, filtrado de series y enlaces persistentes | PASS |
| Rechazo de inyección, coincidencias amplias, traversal, 0666 y grupos inválidos | PASS |
| CRUD, habilitación de borrador, backup/restauración y verificación posterior | PASS |
| Fallo de escritura, metadata corrupta, FIFO y enlaces simbólicos | PASS |
| CLI JSON y rechazo de operación de instalación | PASS |
| Reglas generadas contrastadas con `udevadm verify` del host | PASS |
| Inventario host y muestras de detalle/permisos de solo lectura | PASS |
| Página QML y primitivas reales, registro/búsqueda, worker y CRUD con estado aislado | PASS |
| Preparación desde interfaz elegible, guardado desde formulario y retorno al origen | PASS |
| Parsing de todos los QML de la función con herramientas Qt 6 | PASS |
| Dos columnas a 1.250 px, navegación estrecha a 460 px, ratón/teclado y búsqueda | PASS |
| Fixtures de 1.500 nodos: presupuesto de filas, búsqueda sin ancestros y paginación final | PASS |
| CPU de cuatro hilos/dos núcleos, teclado con tres hidraw, GPU/DRM, hubs y Bluetooth | PASS |
| Layout sin binding loops ni avisos de reajuste recursivo | PASS |
| Layout offscreen con tokens de prueba | PASS; no sustituye el tema real |
| Suscripción y desconexión/reconexión física en sesión real | SKIP: monitor no disponible en el sandbox; fallback manual comprobado |
| Polkit, instalación/rollback de reglas, controles de hardware | SKIP: capacidades deliberadamente no implementadas |
| Pruebas visuales del usuario con tema claro/oscuro y transparencia | SKIP: pendientes del usuario |

No quedaron fallos conocidos en las 15 pruebas enfocadas al entregar el rediseño.
Los conteos del host pueden variar por dispositivos virtuales y procesos de prueba.
No se ejecutó la suite global ni se arrancó/reinició la sesión del usuario.

Para la validación del usuario, abrir Settings normalmente o ejecutar
`./dev settings` **cuando decida abrir su instancia de desarrollo**, ir a
Sistema → Hardware → Dispositivos, elegir una categoría y buscar USB/PCI/hidraw. Seleccionar un dispositivo y su
controlador; comparar ficha y permisos con sus herramientas habituales. Probar
Conexiones, expansión manual y modo técnico; revisar driver sin módulo separado, dispositivos sin firmware y
reconexión física. En una interfaz compatible, revisar el alcance, guardar un
borrador, editarlo, deshabilitarlo, borrarlo y restaurar la colección anterior.
Verificar que todos siguen indicando «sin instalar». Revisar textos, navegación
por teclado, contraste claro/oscuro y transparencia. Ningún paso requiere reglas
preexistentes del usuario como ejemplo ni como entrada de pruebas.

Comprobar además una ventana ancha con inventario e inspector adyacentes, y una
angosta con Volver. En Conexión e interfaces seleccionar un hidraw y volver al
componente; en Acceso y permisos preparar un borrador y regresar al mismo origen.
Verificar Otros/Virtuales bajo demanda, búsqueda sin expansión masiva y los
controles Mostrar más / Resultados siguientes en universos grandes. El agente
no reinició la sesión, no instaló paquetes ni modificó reglas/ACL del host.
