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
- Trece páginas por función; se eliminan las categorías ambiguas General,
  Interface y Advanced y los controles duplicados de la antigua página Quick.
- Encabezados descriptivos, secciones en tarjetas y contenido adaptable al ancho.
- Se conservan las claves y valores existentes; ventana al 80 % del área útil
  del monitor enfocado al abrir. Settings usa un panel centrado de tamaño fijo,
  sin movimiento ni redimensionamiento; se cierra con X o Ctrl+W. Se toma una
  sola medida por apertura, considerando orientación, escala y área reservada.
  Se espera la información inicial de foco antes de elegir la pantalla y mostrarlo.
  Superficie real verificada: vertical 1152 × 2012 y horizontal 2048 × 1116.
- Verificación: carga de las trece páginas, búsqueda con acentos, navegación
  circular y búsqueda sin resultados; revisión visual amplia y compacta.

## 2. Configuración visual de Hyprland — pendiente

- Monitores: posición, resolución, frecuencia, escala y orientación.
- Ventanas, bordes, espacios, efectos y dispositivos de entrada.
- Persistencia separada, aplicación controlada y recuperación ante fallos.

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
