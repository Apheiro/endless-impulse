{
  description = "Artificial Impulse: Hyprland shell with locked upstream dependencies";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    shapes = {
      url = "github:end-4/rounded-polygon-qmljs/e31ec4cb4ebf6a46b267f5c42eabf6874916fa16";
      flake = false;
    };
  };

  outputs = { self, nixpkgs, shapes }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      eachSystem = nixpkgs.lib.genAttrs systems;
    in {
      packages = eachSystem (system:
        let pkgs = import nixpkgs { inherit system; };
        in rec {
          default = pkgs.callPackage ./packaging/nix/package.nix { source = self; inherit shapes; };
          math-runtime = default.passthru.mathRuntime;
        });
      apps = eachSystem (system: {
        default = { type = "app"; program = "${self.packages.${system}.default}/bin/dots-hyperland"; };
        settings = { type = "app"; program = "${self.packages.${system}.default}/bin/dots-hyperland-settings"; };
        services = let pkgs = import nixpkgs { inherit system; }; in {
          type = "app";
          program = "${pkgs.writeShellScript "artificial-impulse-services" ''
            exec ${pkgs.python3}/bin/python3 ${self}/packaging/nix/services.py "$@"
          ''}";
        };
      });
      devShells = eachSystem (system:
        let pkgs = import nixpkgs { inherit system; };
        in { default = pkgs.mkShell {
          inputsFrom = [ self.packages.${system}.default ];
          packages = [ pkgs.git pkgs.qt6.qtdeclarative self.packages.${system}.default.python pkgs.nodejs pkgs.lua ];
          DOTS_MATH_RUNTIME = "${self.packages.${system}.default.mathRuntime}";
          DOTS_XKBCOMMON_LIBRARY = "${pkgs.libxkbcommon}/lib/libxkbcommon.so.0";
          GI_TYPELIB_PATH = self.packages.${system}.default.giPath;
          DOTS_TEST_LAUNCHER = "${self.packages.${system}.default}/bin/dots-hyperland";
        }; });
    };
}
