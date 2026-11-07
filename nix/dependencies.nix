# SPDX-License-Identifier: MIT
{
  lib,
  stdenv,
  callPackage,
  runCommand,
  fetchgit,
  unzip,
  zstd,
  purifier,
}:
{
  lock,
  fetchers ? { },
}:
let
  target = import ./host-platform.nix {
    inherit lib;
    system = stdenv.hostPlatform.system;
  };
in
purifier.tree (
  {
    name = "docker-dependencies";
    entries = lib.filter (e: builtins.elem target.system e.systems) (purifier.checkLock lock).entries;
    fetchurl = callPackage ./fetch-blob.nix { };
    inherit
      runCommand
      fetchgit
      unzip
      zstd
      ;
  }
  // fetchers
)
