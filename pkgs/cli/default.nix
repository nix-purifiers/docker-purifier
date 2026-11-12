# SPDX-License-Identifier: MIT
{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  nix,
  docker-client,
  docker-buildx,
  dockerfile-language-server,
  skopeo,
  gh,
  cacert,
  nixpkgsSrc,
  purifierSrc,
}:
stdenvNoCC.mkDerivation {
  pname = "docker-purifier";
  version = "0.1.0";
  src = ../..;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  passthru = {
    nativeDocker = docker-client;
    nativeSkopeo = skopeo;
  };
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/docker-purifier"
    cp -r docker_purifier pkgs lib-overlays tests "$out/lib/docker-purifier/"
    install -m755 bin/docker-purifier "$out/bin/docker-purifier"
    substituteInPlace "$out/lib/docker-purifier/pkgs/build-docker-project/realize.nix" \
     --replace-fail '@nixpkgs@' '${nixpkgsSrc}' \
     --replace-fail '@purifier@' '${purifierSrc}' \
     --replace-fail '@runtime@' "$out"
    wrapProgram "$out/bin/docker-purifier" \
     --prefix PATH : ${
       lib.makeBinPath [
         python3
         nix
         docker-client
         docker-buildx
         skopeo
         gh
       ]
     } \
     --prefix PYTHONPATH : "$out/lib/docker-purifier" \
     --set DOCKER_PURIFIER_DOCKER ${docker-client}/bin/docker \
     --set DOCKER_PURIFIER_SKOPEO ${skopeo}/bin/skopeo \
     --set DOCKER_PURIFIER_REALIZE "$out/lib/docker-purifier/pkgs/build-docker-project/realize.nix" \
     --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
     --prefix DOCKER_CLI_PLUGIN_DIRS : ${docker-buildx}/libexec/docker/cli-plugins
    makeWrapper "$out/bin/docker-purifier" "$out/bin/docker" --add-flags "native --"
    ln -s ${dockerfile-language-server}/bin/docker-langserver "$out/bin/docker-langserver"
  '';
  meta = {
    description = "Locked Nix-resolved Docker base images";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux ++ [ "x86_64-darwin" ];
    mainProgram = "docker-purifier";
    homepage = "https://nix-purifiers.github.io/";
  };
}
