# SPDX-License-Identifier: MIT
{ lib }:
let
  cases = {
    x86_64-linux = [
      "linux/amd64"
      "x86_64-linux"
    ];
    x86_64-darwin = [
      "linux/amd64"
      "x86_64-linux"
    ];
    aarch64-linux = [
      "linux/arm64"
      "aarch64-linux"
    ];
    aarch64-darwin = [
      "linux/arm64"
      "aarch64-linux"
    ];
  };
  verify =
    host: expected:
    let
      target = import ../nix/host-platform.nix {
        inherit lib;
        system = host;
      };
      selected =
        import ../nix/dependencies.nix
          {
            inherit lib;
            stdenv.hostPlatform.system = host;
            callPackage = _: _: null;
            runCommand = null;
            fetchgit = null;
            unzip = null;
            zstd = null;
            purifier = {
              tree = x: x;
              checkLock = x: x;
            };
          }
          {
            lock.entries =
              map
                (system: {
                  inherit system;
                  systems = [ system ];
                })
                [
                  "x86_64-linux"
                  "aarch64-linux"
                ];
          };
    in
    assert target.platform == builtins.elemAt expected 0;
    assert target.system == builtins.elemAt expected 1;
    assert map (entry: entry.system) selected.entries == [ target.system ];
    true;
in
assert builtins.all (host: verify host cases.${host}) (builtins.attrNames cases);
true
