# SPDX-License-Identifier: MIT
{
  project,
  dockerfile,
  lockFile,
  target,
}:
let
  pkgs = import (builtins.toPath "@nixpkgs@") { };
  purifier = import (builtins.toPath "@purifier@/nix/lib") { inherit (pkgs) lib; };
  read = (import ./read-lock.nix { inherit (pkgs) lib; }) {
    src = /. + project;
    lockFile = /. + lockFile;
    dockerfile = /. + dockerfile;
  };
  result = pkgs.callPackage ./build-project.nix { inherit purifier; } {
    src = /. + project;
    lockFile = /. + lockFile;
    dockerfile = /. + dockerfile;
  };
in
if target == "dependencies" then
  pkgs.callPackage ./dependencies.nix { inherit purifier; } { lock = purifier.checkLock read; }
else if target == "runtime" then
  pkgs.runCommand "docker-runtime" { } ''ln -s @runtime@ "$out"''
else if target == "release" then
  result.release
else
  throw "docker-purifier: invalid target"
