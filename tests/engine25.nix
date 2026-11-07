# SPDX-License-Identifier: MIT
# Moby's maintained 25.x patch releases have no Docker CE static tarball.
# Build the immutable upstream daemon with nixpkgs' existing 25.x runtime set.
{ pkgs }:
let
  version = "25.0.18";
  revision = "eaa0057b5d603fbd1eb1867246c05ef2a0cf1ed9";
in
pkgs.docker_25.moby.overrideAttrs (old: {
  inherit version;
  src = pkgs.fetchFromGitHub {
    owner = "moby";
    repo = "moby";
    rev = revision;
    hash = "sha256-HORhTu8QGuBOO3vi06XWZHvm+KQHbYirzLZsdv2NGto=";
  };
  buildPhase =
    pkgs.lib.replaceStrings
      [ old.version "43987fca488a535d810c429f75743d8c7b63bf4f" ]
      [ version revision ]
      old.buildPhase;
})
