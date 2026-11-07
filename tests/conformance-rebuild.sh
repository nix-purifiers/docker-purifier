#!/usr/bin/env bash
set -euo pipefail
system="$(nix eval --impure --raw --expr builtins.currentSystem)"
for output in image release; do
  nix build ".#checks.${system}.${output}" --option sandbox true --no-link
  nix build ".#checks.${system}.${output}" --option sandbox true --no-link --rebuild
done
