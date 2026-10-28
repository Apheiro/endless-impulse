# Artificial Impulse — Roadmap

Base: dependencias upstream y entorno Nix fijado. Referencia funcional:
`pctrade/end4-pC` en `74813a8219defc8d210c2055d6935fbfb9f93239`.
Adaptar funciones por etapas, conservando licencias, preferencias y el editor
de shortcuts. El usuario valida cada etapa; los commits se crean solo cuando
los solicite.

## 1. Eventos y estabilidad — implementada; aceptación manual pendiente

- Agrupar ráfagas de eventos con un plazo máximo de 60 ms.
- Consultar únicamente ventanas, escritorios, monitores o capas afectados.
- Conservar actualizaciones que lleguen mientras una consulta sigue en curso.
- No reasignar datos idénticos; conservar el último estado válido ante errores.
- Validar con IPC simulado y luego con apertura/cierre de apps, cambios de foco,
  escritorios y paneles en la sesión real. No dar por resuelto el congelamiento
  sin reproducción y validación del usuario.

Verificación automática: 25 pruebas aprobadas, incluidas ráfagas, consultas lentas,
respuestas inválidas/idénticas y flujo continuo de eventos. Una ráfaga simulada
de 40 aperturas genera tres consultas adicionales, sin consultar monitores ni
capas otra vez.
La carga de tipos de ambas interfaces también se verifica. Se protegieron el
reloj, el filtro nocturno y la respuesta del traductor durante recargas.
También se corrigieron el enrutamiento de IPC a la instancia activa, la comprobación
de Super y la convivencia de la bandeja con su registro compartido. La detección
de iconos sigue siendo dinámica; Steam fue verificado por el usuario.

## Base de Settings — implementada; aceptación manual pendiente

- Navegación con nombres visibles, cuatro grupos y filtro por tema.
- Dieciséis páginas por función; se eliminan las categorías ambiguas General,
  Interface y Advanced y los controles duplicados de la antigua página Quick.
- Encabezados descriptivos, secciones en tarjetas y contenido adaptable al ancho.
- Se conservan las claves y valores existentes; ventana al 80 % del área útil
  del monitor enfocado al abrir. Settings usa un panel centrado de tamaño fijo,
  sin movimiento ni redimensionamiento; se cierra con X o Ctrl+W. Se toma una
  sola medida por apertura, considerando orientación, escala y área reservada.
  Se espera la información inicial de foco antes de elegir la pantalla y mostrarlo.
  Superficie real verificada: vertical 1152 × 2012 y horizontal 2048 × 1116.
- Verificación: carga de las dieciséis páginas, búsqueda con acentos, navegación
  circular y búsqueda sin resultados; revisión visual amplia y compacta.

## 2. Configuración visual de Hyprland — implementada; aceptación manual pendiente

- Monitores: mapa seleccionable y arrastrable, colocación relativa, resolución,
  frecuencia, escala y las ocho orientaciones. Se conservan las coordenadas reales.
- Ventanas y efectos: layout, espacios, bordes y sus colores, redondeado,
  opacidad, desenfoque, sombras, animaciones y comportamiento de foco/divisiones.
- Entrada: distribución y opciones de teclado, repetición, mouse, touchpad y
  overrides por dispositivo. Se leen 39 opciones reales; las no soportadas se deshabilitan.
- Tres páginas nuevas en Settings: Monitors, Windows & effects y Keyboard & mouse.
  Abrirlas no aplica valores. Los controles editan un borrador compartido.
- Overrides propios en `artificial-impulse/hyprland.json` y `hyprland.lua`, cargados
  después de la configuración personal mediante un módulo y una línea de integración.
- Prueba de 20 segundos y confirmación en un panel compacto independiente. Un
  guardián separado restaura el estado previo aunque se cierre Settings; una sesión
  nueva no carga previews sin confirmar. Se conserva el archivo anterior y se
  restaura la geometría real de los monitores. Hay recuperación manual por CLI.
- Verificación: 48 pruebas, incluyendo procesos separados para el guardián, errores
  de configuración, vencimiento, reintentos, carga Lua, validación y las 16 páginas.
  Revisión visual con datos reales. El usuario valida la aplicación y confirmación
  de cambios en su hardware; no se han probado automáticamente nuevos modos reales.

## Dock: minimización — implementada; aceptación manual pendiente

- Clic en la ventana enfocada para minimizar; clic para restaurar o enfocar.
- Acciones por ventana en las previews, iconos conservados e indicadores huecos.
- Workspace propio `special:artificial-minimized`, separado del scratchpad.
- Origen persistido por sesión y PID; limpieza de ventanas cerradas, recuperación
  de ventanas huérfanas y comando `restore-all`. No se minimizan grupos ni ventanas
  fijadas accidentalmente. El dock muestra los errores de esas acciones.
- Previews a aproximadamente 1 FPS solo cuando están visibles; captura única
  antes de minimizar y caché RAM compartida de hasta 24 imágenes de 300 × 200.
  Se desconecta la captura después de cada frame y se eliminan imágenes al cerrar
  ventanas o bloquear la pantalla. No se guardan capturas en disco.
- Prueba con una ventana propia: verifica colores reales, congelamiento al
  minimizar, actualización al restaurar, pausa al ocultar y liberación al cerrar.
- Diez pruebas simuladas y una ventana descartable real verificaron minimizar y
  restaurar al workspace de origen. Queda la validación del usuario con sus apps.

## 3. Barra configurable y presets — pendiente

- Selección, orden y estilo de componentes de barra/dock.
- Presets locales: guardar, previsualizar, importar, exportar y restaurar.
- Revisar compatibilidad y datos personales antes de agregar una galería online.

## 4. Widgets y multimedia — pendiente

- Calendario, reloj mundial, notas, tareas, temporizadores y recursos.
- Reproductor, letras sincronizadas y ecualizador con presets.
- Fondos online/collages y widgets de imágenes según prioridad de uso.

Todas las etapas usan `./dev check`; las pruebas automáticas y la aceptación
manual se registran por separado. Actualizar dependencias únicamente cuando
una función lo requiera.
