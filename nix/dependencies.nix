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
purifier.tree (
  {
    name = "docker-dependencies";
    entries = lib.filter (
      e: builtins.elem stdenv.hostPlatform.system e.systems
    ) (purifier.checkLock lock).entries;
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
