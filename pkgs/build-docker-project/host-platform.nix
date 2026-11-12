# SPDX-License-Identifier: MIT
# Docker's Linux image architecture is independent of the client host OS.
{ lib, system }:
let
  architecture = (lib.systems.elaborate system).parsed.cpu.name;
  targets = {
    x86_64 = {
      platform = "linux/amd64";
      system = "x86_64-linux";
    };
    aarch64 = {
      platform = "linux/arm64";
      system = "aarch64-linux";
    };
  };
in
targets.${architecture}
  or (throw "docker-purifier: unsupported client architecture ${architecture}")
