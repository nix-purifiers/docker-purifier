# SPDX-License-Identifier: MIT
{
  description = "Locked, Nix-resolved dependencies for Docker";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.nixpkgs-intel-darwin.url = "github:NixOS/nixpkgs/nixpkgs-26.05-darwin";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
      nixpkgs-intel-darwin,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      shared = lib: import (purifier + "/nix/lib") { inherit lib; };
      overlay = final: prev: {
        docker-purifier = final.lib.makeScope final.newScope (scope: {
          cli = scope.callPackage ./pkgs/cli/default.nix {
            nixpkgsSrc = final.path;
            purifierSrc = purifier;
          };
          buildDockerProject = scope.callPackage ./pkgs/build-docker-project/default.nix {
            purifier = shared final.lib;
          };
        });
      };
      pkgsFor =
        system:
        import (if system == "x86_64-darwin" then nixpkgs-intel-darwin else nixpkgs) {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      lib.docker-purifier = (nixpkgs.lib.extend (import ./lib-overlays/default)).docker-purifier;
      packages = forAll (
        system:
        {
          default = (pkgsFor system).docker-purifier.cli;
          cli = self.packages.${system}.default;
        }
        // nixpkgs.lib.optionalAttrs (nixpkgs.lib.hasSuffix "-linux" system) {
          test-engine25 = import ./tests/engine25.nix { pkgs = pkgsFor system; };
        }
      );
      apps = forAll (system: {
        default = {
          type = "app";
          meta.description = "Lock and prefetch Docker dependencies";
          program = "${self.packages.${system}.default}/bin/docker-purifier";
        };
      });
      devShells = forAll (system: {
        default = (pkgsFor system).mkShell {
          packages = [
            self.packages.${system}.default
            (pkgsFor system).python3
          ];
        };
      });
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
      checks = forAll (
        system:
        import ./tests {
          pkgs = pkgsFor system;
          inherit self;
        }
      );
    };
}
