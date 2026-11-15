# Superficies internas: factibilidad de XEmbed

Actualización 2026-11-09: el usuario autorizó implementar pese al límite de
validación de esta etapa. Ver [implementación y pruebas](../features/internal-surfaces.md).
La conclusión siguiente se conserva como antecedente; ya no bloquea el desarrollo.

Fecha: 2026-11-08. Etapa 1 cerrada: **INCONCLUSA**. Etapa 2 detenida.
No hay un fallo funcional reproducido ni una validación que permita activar
`special:endless-internal` por defecto.

## Alcance y entorno

Inspección de código local y fuentes upstream; ninguna modificación de la
sesión, configuración instalada, procesos ni preferencias. No se ejecutaron
`./dev run`, `./dev settings`, reinicios, reglas IPC ni clics sintéticos.

La base de paquetes local informa Hyprland `0.56.2-4`, Xwayland `24.1.14-1`,
Plasma Workspace `6.8.1-1` y Quickshell `0.3.2-1`. Esto identifica paquetes
instalados, no demuestra qué binarios ejecuta la sesión o el runtime Nix.
Las fuentes consultadas de Hyprland corresponden al tag `v0.56.2`; para KDE
se pudo consultar la rama `Plasma/6.8`, pero no recuperar el archivo del tag
`v6.8.1`. No se afirma equivalencia exacta con el binario instalado.

## Evidencia y límite técnico

- [XEmbed](https://specifications.freedesktop.org/xembed/latest-single/)
  usa ventanas X11, reparenting y mensajes entre cliente y contenedor. El
  protocolo no establece garantías sobre workspaces especiales de Hyprland.
- El [proxy KDE](https://raw.githubusercontent.com/KDE/plasma-workspace/Plasma/6.8/xembed-sni-proxy/sniproxy.cpp)
  crea un contenedor de clase `xembedsniproxy`, de 32 píxeles y
  `override_redirect`, lo mapea y redirige al hijo mediante XComposite.
  La imagen se publica por SNI. En `sendClick`, reposiciona el contenedor,
  habilita su región de entrada y, en Wayland, solicita mover el puntero al
  hijo. Usa eventos directos o XTest según el cliente. La ruta XTest mantiene
  brevemente activa la entrada. Por ello, conservar un pixmap no demuestra
  que activación, menú y scroll funcionen en un workspace cerrado. Ocultarlo
  tampoco elimina esas operaciones de geometría e interacción.
- [Xwayland](https://wayland.freedesktop.org/docs/book/Xwayland.html)
  es un servidor X que actúa como cliente Wayland. Una prueba solo con Xvfb
  no reproduce su integración con el compositor.
- El [renderer de Hyprland 0.56.2](https://raw.githubusercontent.com/hyprwm/Hyprland/v0.56.2/src/render/Renderer.cpp)
  condiciona el render normal a visibilidad y workspace. `render_unfocused`
  proporciona feedback y desbloquea estados de superficies fuera del render
  normal; no constituye una garantía de entrega de entrada a ventanas en un
  workspace especial oculto. En
  [Window.cpp](https://raw.githubusercontent.com/hyprwm/Hyprland/v0.56.2/src/desktop/view/Window.cpp),
  la suspensión XDG excluye clientes X11: no corresponde trasladar sin más
  las conclusiones sobre suspensión de clientes Wayland a este proxy.
- [Quickshell SystemTrayItem](https://quickshell.org/docs/v0.3.0/types/Quickshell.Services.SystemTray/SystemTrayItem/)
  expone icono, activación, menú y scroll por su integración SNI. Esa API no
  ofrece una garantía sobre el contenedor XEmbed subyacente.

**Inferencia:** la captura puede ser compatible con mantener el contenedor
mapeado en un workspace oculto, pero la interacción requiere comprobar las
rutas directas y XTest. No se demostró que falle siempre ni que funcione sin
efectos sobre foco, puntero o menús. Esto impide superar la condición de
entrada a la etapa 2.

## Situación del repositorio

`src/quickshell/shell.qml` inicia el puente cuando está disponible.
`services/LayerEffects.qml` conserva la regla visual existente; este trabajo
no la cambia ni la considera solución final.

`services/HyprlandData.qml` conserva el inventario de clientes, aunque filtra
la lista de workspaces ordinarios. `services/TaskbarApps.qml` enumera los
toplevels sin excluir un workspace interno; lo consumen dock y barra Windows.
El overview filtra por rango de workspace ordinario. Por tanto, trasladar
ventanas no basta para garantizar la exclusión de todas las vistas. No se
validó un switcher externo ni el recorrido completo de alt-tab.

`services/WindowMinimizer.qml` y `scripts/hyprland/minimize.py` reservan
`special:artificial-minimized`; no deben reutilizarse para este propósito.

## Verificaciones realizadas

| Verificación | Resultado | Alcance |
| --- | --- | --- |
| Versiones instaladas | PASS | Consulta local de paquetes, sin ejecutar servicios |
| Revisión del flujo XEmbed/SNI y código local | PASS | Inspección estática; no validación funcional |
| Captura y refresco con workspace cerrado | SKIP | Sin compositor de prueba y cliente legado instrumentado |
| Clic, menú, scroll, foco y puntero | SKIP | No se inyectó entrada en la sesión del usuario |
| Exclusión completa dock/overview/alt-tab | SKIP | Solo inspección; no implementación |
| Persistencia, arranque y reload | SKIP | Etapa 2 no iniciada |
| Sintaxis y tests de implementación | SKIP | Únicamente se añadió este documento |

## Alternativas y siguiente decisión

1. **Validación aislada, recomendada:** usar una sesión de prueba separada,
   con configuración, runtime y bus D-Bus propios, Hyprland 0.56.2 y su
   Xwayland. Comprobar primero el comportamiento base, luego el workspace
   especial cerrado. Incluir un icono dinámico con entrada directa y otro
   con XTest; registrar cambios de imagen, contadores de clic izquierdo,
   medio, menú y scroll, foco y posición del puntero. Comprobar ventanas de
   menú y apertura de la aplicación. No basta un icono estático. Esta sesión
   no se ha preparado ni ejecutado en este turno.
2. Si esa prueba falla, evaluar un cambio acotado en el puente o integración
   del compositor para las superficies auxiliares. Es trabajo adicional,
   sin solución upstream headless demostrada; no se propone simular su éxito
   con transparencia o posición fuera de pantalla.
3. Reducir el alcance a inventario de solo lectura en Settings, sin ocultar
   superficies, si el usuario elige avanzar con esa funcionalidad parcial.

Una prueba futura sobre el escritorio vivo necesita aprobación adicional.
Debe especificar cliente e identificadores exactos, registrar el origen de
cada superficie y restaurar de forma idempotente workspace, geometría y
reglas temporales incluso ante error. No debe mover todas las ventanas de
un PID, matar procesos, ni mezclar superficies con ventanas minimizadas.

Solo después de una validación satisfactoria procede implementar el
administrador: inventario por superficie, reglas persistentes con identidad
auxiliar comprobada, coincidencias exactas sin patrones amplios, detección
de duplicados, xembedsniproxy preconfigurado, reconciliación tras arranque y
reload y exclusión compartida en vistas de ventanas. Nombre, PID o tamaño
aislados no prueban que una ventana sea auxiliar; las entradas ambiguas
deben rechazarse. No se implementó este diseño ni se alteraron preferencias.
