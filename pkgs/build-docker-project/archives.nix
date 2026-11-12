# SPDX-License-Identifier: MIT
{
  lib,
  stdenv,
  runCommand,
  writeText,
  python3,
  skopeo,
}:
{ lock, dependencies }:
let
  target = import ./host-platform.nix {
    inherit lib;
    system = stdenv.hostPlatform.system;
  };
  platform = target.platform;
  alias = ref: builtins.substring 0 20 (builtins.hashString "sha256" ref);
  policy = writeText "docker-archive-policy.json" (
    builtins.toJSON {
      default = [ { type = "reject"; } ];
      transports.oci."" = [ { type = "insecureAcceptAnything"; } ];
    }
  );
in
runCommand "docker-native-archives"
  {
    nativeBuildInputs = [
      python3
      skopeo
    ];
  }
  ''
    mkdir -p "$out"
    ${lib.concatMapStringsSep "\n" (
      ref:
      let
        key = alias ref;
        manifest = builtins.fromJSON lock.images.${ref}.platforms.${platform}.manifest;
        tag = "localhost/nix-purifier-base:${lib.removePrefix "sha256:" manifest.config.digest}";
        layout = "${dependencies}/${key}/${target.system}";
      in
      ''
        skopeo --tmpdir "$TMPDIR" --policy ${policy} copy oci:${layout}:purifier docker-archive:"$TMPDIR/${key}.tar":${tag}
        python ${../../docker_purifier/archive.py} "$TMPDIR/${key}.tar" "$out/${key}.tar" "$out/${key}.json" ${lib.escapeShellArg tag}
      ''
    ) (builtins.attrNames lock.images)}
  ''
