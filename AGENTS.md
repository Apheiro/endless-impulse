# Proyecto
Artificial Impulse: escritorio Hyprland/Wayland, fork de illogical-impulse, con dependencias upstream independientes. Interfaz: Quickshell (Qt 6, QML y JavaScript); configuración: Lua; integración: Bash y Python; temas: Matugen; fórmulas: MathJax/Node.js.

# Estructura
- `dots/`: configuraciones; `dots/.config/quickshell/ii/`: interfaz, componentes, servicios y scripts.
- `dots/.config/hypr/`: ventanas, atajos y arranque.
- `sdata/`: instalador y dependencias por distribución; `dots-extra/`: variantes.
- `setup`: instalación, actualización y desinstalación.
- `nix/`, `flake.lock`: entorno reproducible; `sdata/dependencies/arch.json`: paquetes normales de Arch.

# Trabajo
- Seguir las convenciones existentes; mantener cambios enfocados y conservar licencias y atribuciones.
- Desarrollar con `./dev run`, `./dev settings` y `./dev check`; QML se recarga al guardar. `./dev restart` reinicia esta instancia. No actualizar locks sin necesidad; revisar errores y comprobar la función modificada.
- La ejecución usa la sesión y preferencias del usuario; no es una prueba aislada. No ejecutar `./setup install` ni reemplazar configuraciones personales sin una solicitud explícita.
- Consultar `.github/CONTRIBUTING.md` y `sdata/deps-info.md` para desarrollo y dependencias.
- El usuario es el tester principal; distinguir las verificaciones del agente de las pruebas y validaciones del usuario.

# Git
- El agente gestiona Git. Acumular cambios sin commitear hasta que el usuario lo indique explícitamente; agruparlos por propósito en commits coherentes.
- Usar Conventional Commits para releases: `tipo(alcance): resumen` (`feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `build`, `ci`, `chore`; alcance opcional). Marcar incompatibilidades con `!` y explicar `BREAKING CHANGE:` en el cuerpo.
- No crear tags, publicar releases ni hacer push sin indicación del usuario.
