{ lib, stdenvNoCC, pkgs, makeWrapper, source, shapes, buildNpmPackage }:
let
  storageRuntime = pkgs.rustPlatform.buildRustPackage {
    pname = "endless-storage";
    version = "0.1.0";
    src = builtins.path { path = source + /runtime/storage; name = "endless-storage-source"; filter = path: type: builtins.baseNameOf path != "target"; };
    cargoLock.lockFile = source + /runtime/storage/Cargo.lock;
    nativeCheckInputs = [ pkgs.coreutils ];
  };
  mathRuntime = buildNpmPackage {
    pname = "dots-hyperland-math";
    version = "1.0.0";
    src = builtins.path { path = source + /runtime/math; name = "dots-math-source"; };
    npmDepsHash = "sha256-vHrfpEQg1JLFxyMSYmGWB4Qp1AGs1V7B4B6zjOswww8=";
    npmFlags = [ "--ignore-scripts" ];
    dontNpmBuild = true;
    dontNpmInstall = true;
    installPhase = ''
      mkdir -p $out
      cp -r package.json package-lock.json node_modules $out/
    '';
  };
  python = pkgs.python3.withPackages (ps: with ps; [
    pillow psutil pygobject3 pycairo numpy opencv4 requests google-auth click loguru
    tqdm materialyoucolor material-color-utilities libsass setproctitle pywayland kde-material-you-colors
  ]);
  tools = import ./runtime.nix { inherit pkgs; };
  fonts = with pkgs; [ material-symbols rubik twemoji-color-font readexpro nerd-fonts.jetbrains-mono ];
  fontConfig = pkgs.makeFontsConf { fontDirectories = fonts; };
  introspection = with pkgs; [ networkmanager (lib.getLib networkmanager) glib gobject-introspection gnome-desktop gsettings-desktop-schemas gtk4 gtk3 gdk-pixbuf pango atk libadwaita libsoup_3 ];
  qmlPackages = with pkgs; [
    qt6.qtbase qt6.qtdeclarative qt6.qt5compat qt6.qtimageformats qt6.qtmultimedia
    qt6.qtpositioning qt6.qtquicktimeline qt6.qtsensors qt6.qtsvg qt6.qtvirtualkeyboard
    qt6.qtwayland kdePackages.kirigami kdePackages.syntax-highlighting
  ];
in stdenvNoCC.mkDerivation {
  pname = "dots-hyperland";
  version = "0.1.0";
  src = source + /src/quickshell;
  nativeBuildInputs = [ makeWrapper pkgs.qt6.wrapQtAppsHook pkgs.qt6.qtshadertools ];
  buildInputs = qmlPackages;
  dontWrapQtApps = true;
  dontBuild = true;
  postPatch = ''
    # Export the exact installer dependency reference for offline installed builds.
    ${python}/bin/python3 ${source}/src/quickshell/scripts/system/dependencies.py \
      --root ${source} --snapshot > defaults/dependencies.json
    # Replace legacy virtualenv shebangs with the locked interpreter in the bundle.
    find . -name '*.py' -exec sed -i '1s|^#!.*|#!${python}/bin/python3|' {} +
    ${pkgs.qt6.qtshadertools}/bin/qsb --qt6 \
      -o modules/shared/widgets/shaders/color-tint.frag.qsb \
      modules/shared/widgets/shaders/color-tint.frag
  '';
  installPhase = ''
    mkdir -p $out/share/dots-hyperland/.config/quickshell/endless-Impulse $out/share/dots-hyperland/.local/share $out/bin $out/lib/python-env/bin
    cp ${source}/packaging/nix/host-graphics.py $out/lib/host-graphics.py
    cp -r ./. $out/share/dots-hyperland/.config/quickshell/endless-Impulse/
    cp -r ${source}/config/xdg/config/. $out/share/dots-hyperland/.config/
    cp -r ${source}/config/xdg/data/. $out/share/dots-hyperland/.local/share/
    mkdir -p $out/share/dots-hyperland/.config/quickshell/endless-Impulse/runtime/storage
    ln -s ${storageRuntime}/bin/endless-storage $out/share/dots-hyperland/.config/quickshell/endless-Impulse/runtime/storage/endless-storage
    shapeDir=$out/share/dots-hyperland/.config/quickshell/endless-Impulse/modules/shared/widgets/shapes
    rm -rf "$shapeDir"
    cp -r ${shapes} "$shapeDir"
    cat > $out/lib/python-env/bin/activate <<'ACTIVATE'
    export PATH=${python}/bin:$PATH
    deactivate() { :; }
    ACTIVATE
    for name in dots-hyperland dots-hyperland-settings; do
      entry=""
      if [ "$name" = dots-hyperland-settings ]; then entry="/settings.qml"; fi
      makeShellWrapper ${python}/bin/python3 $out/bin/$name \
        --prefix PATH : ${lib.makeBinPath ([ python pkgs.quickshell ] ++ tools)} \
        --prefix XDG_DATA_DIRS : ${lib.makeSearchPath "share" tools} \
        --set FONTCONFIG_FILE ${fontConfig} \
        --prefix GI_TYPELIB_PATH : ${lib.makeSearchPath "lib/girepository-1.0" introspection} \
        --set DOTS_XKBCOMMON_LIBRARY ${pkgs.libxkbcommon}/lib/libxkbcommon.so.0 \
        --set DOTS_MESA_VENDOR ${pkgs.mesa}/share/glvnd/egl_vendor.d/50_mesa.json \
        --set DOTS_MESA_DRIVERS ${pkgs.mesa}/lib/dri \
        --set DOTS_MESA_GBM ${pkgs.mesa}/lib/gbm \
        --set DOTS_MATH_RUNTIME ${mathRuntime} \
        --set DOTS_STORAGE_EXECUTABLE ${storageRuntime}/bin/endless-storage \
        --set DOTS_SHELL_LAUNCHER "$out/bin/dots-hyperland" \
        --set ILLOGICAL_IMPULSE_VIRTUAL_ENV $out/lib/python-env \
        --set-default DOTS_SHELL_SOURCE "$out/share/dots-hyperland/.config/quickshell/endless-Impulse" \
        --add-flags "$out/lib/host-graphics.py ${pkgs.quickshell}/bin/quickshell" \
        --add-flags '-p "$DOTS_SHELL_SOURCE'"$entry"'"'
    done
    makeShellWrapper ${python}/bin/python3 $out/bin/dots-shell \
      --add-flags "$out/share/dots-hyperland/.config/quickshell/endless-Impulse/scripts/shell/control.py"
  '';
  preFixup = ''
    wrapQtApp "$out/bin/dots-hyperland"
    wrapQtApp "$out/bin/dots-hyperland-settings"
  '';
  passthru = {
    inherit mathRuntime storageRuntime python tools;
    giPath = lib.makeSearchPath "lib/girepository-1.0" introspection;
    runtimeVersions = {
      quickshell = pkgs.quickshell.version;
      qt = pkgs.qt6.qtbase.version;
      python = python.python.version;
      mathjax = (builtins.fromJSON (builtins.readFile (source + /runtime/math/package.json))).dependencies.mathjax;
    };
  };
  meta = {
    description = "Hyprland shell with an independent, reproducible dependency tree";
    license = lib.licenses.gpl3Only;
    platforms = lib.platforms.linux;
    mainProgram = "dots-hyperland";
  };
}
