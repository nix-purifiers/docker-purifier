# SPDX-License-Identifier: MIT
{ pkgs, self }:
let
  fixture = ../examples/hello;
  project = pkgs.docker-purifier.buildDockerProject { src = fixture; };
  externalSource = builtins.path {
    path = fixture;
    name = "docker-external-source";
    filter = path: type: baseNameOf path != "docker-purifier.lock.json";
  };
  external = pkgs.docker-purifier.buildDockerProject {
    src = externalSource;
    lockFile = fixture + "/docker-purifier.lock.json";
    dockerfile = fixture + "/Dockerfile";
  };
  errorCheck =
    case:
    pkgs.runCommand "docker-${case}"
      {
        nativeBuildInputs = [
          pkgs.python3
          pkgs.nix
        ];
        SOURCE = self;
        NIXPKGS_LIB = "${pkgs.path}/lib";
        PURIFIER = self.inputs.purifier;
        PYTHONPATH = self;
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        python ${./eval-errors.py} ${case}
        touch "$out"
      '';
in
{
  image = project.packages.image;
  offline = project.tests;
  release = project.release;
  conformance-external =
    pkgs.runCommand "docker-external-lock" { nativeBuildInputs = [ pkgs.diffutils ]; }
      ''
        test ! -e ${externalSource}/docker-purifier.lock.json
        diff -r ${project.packages.image} ${external.packages.image}
        touch "$out"
      '';
  unit = pkgs.runCommand "docker-unit" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    cp -r ${self} source
    chmod -R u+w source
    cd source
    python -m unittest discover -s tests -v
    touch "$out"
  '';
  editor =
    pkgs.runCommand "docker-editor"
      {
        nativeBuildInputs = [
          pkgs.python3
          pkgs.dockerfile-language-server
        ];
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        cp -r ${fixture} project
        chmod -R u+w project
        cd project
        python ${./editor.py}
        touch "$out"
      '';
}
// pkgs.lib.genAttrs [
  "conformance-stale"
  "conformance-tampered"
  "conformance-missing"
  "conformance-malformed"
] (name: errorCheck (pkgs.lib.removePrefix "conformance-" name))
