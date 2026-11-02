# SPDX-License-Identifier: MIT
{
  lib,
  stdenv,
  callPackage,
  runCommand,
  writeText,
  vmTools,
  buildah,
  python3,
  gnutar,
  gzip,
  purifier,
}:
{
  src,
  lockFile ? src + "/docker-purifier.lock.json",
  dockerfile ? src + "/Dockerfile",
  fetchers ? { },
  srcFilter ?
    path: type:
    !(builtins.elem (baseNameOf path) [
      ".git"
      ".docker-purifier"
      "result"
    ]),
  buildArgs ? { },
  testCommand ? null,
}:
let
  lock = purifier.checkLock (
    (import ./read-lock.nix { inherit lib; }) { inherit src lockFile dockerfile; }
  );
  dependencies = callPackage ./dependencies.nix { inherit purifier; } { inherit lock fetchers; };
  source = lib.cleanSourceWith {
    inherit src;
    filter = srcFilter;
  };
  platform = if stdenv.hostPlatform.system == "x86_64-linux" then "linux/amd64" else "linux/arm64";
  policy = writeText "docker-local-policy.json" (
    builtins.toJSON {
      default = [ { type = "reject"; } ];
      transports = {
        containers-storage."" = [ { type = "insecureAcceptAnything"; } ];
        oci."" = [ { type = "insecureAcceptAnything"; } ];
      };
    }
  );
  guest =
    runCommand "docker-image"
      {
        memSize = 1024;
        QEMU_OPTS = "-machine accel=tcg -nic none";
        nativeBuildInputs = [
          buildah
          python3
        ];
        PYTHONPATH = ../.;
      }
      ''
                mkdir -p /tmp/container-build /tmp/container-storage /tmp/container-run
                cp -r ${source}/. /tmp/container-build/
                chmod -R u+w /tmp/container-build
                cp ${policy} /tmp/policy.json
                mkdir -p "/tmp/container-build/$(dirname ${lib.escapeShellArg lock.dockerfile})"
            cp ${dockerfile} /tmp/container-build/${lib.escapeShellArg lock.dockerfile}
        ${lib.optionalString (builtins.pathExists (dockerfile + ".dockerignore"))
          "cp ${dockerfile + ".dockerignore"} /tmp/container-build/${
            lib.escapeShellArg (lock.dockerfile + ".dockerignore")
          }"
        }
            cd /tmp/container-build
            python -m docker_purifier.sandbox ${lockFile} ${dependencies} ${lib.escapeShellArg platform} ${lib.escapeShellArg lock.dockerfile} ${lib.escapeShellArg (builtins.toJSON buildArgs)}
            ${lib.optionalString (testCommand != null) testCommand}
                buildah --signature-policy /tmp/policy.json --root /tmp/container-storage --runroot /tmp/container-run --storage-driver=vfs \
                  push purifier-result oci:"$out":purifier
      '';
  image = lib.overrideDerivation (vmTools.runInLinuxVM guest) (_: {
    requiredSystemFeatures = [ ];
  });
  tests = runCommand "docker-project-tests" { nativeBuildInputs = [ python3 ]; } ''
    python ${../tests/check-image.py} ${image}
    touch "$out"
  '';
  release =
    runCommand "docker-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        test -e ${tests}
        mkdir -p "$out" source
        cp -r ${source}/. source/
        chmod -R u+w source
        cp ${lockFile} source/docker-purifier.lock.json
        cp ${dockerfile} source/${lib.escapeShellArg lock.dockerfile}
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -C source -cf - . | gzip -n > "$out/source.tar.gz"
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -C ${image} -cf - . | gzip -n > "$out/image.oci.tar.gz"
      '';
in
assert
  builtins.elem platform lock.platforms
  || throw "docker-purifier: missing native platform; run docker-purifier lock";
{
  packages.image = image;
  inherit tests release dependencies;
  fetches = lock.entries;
}
