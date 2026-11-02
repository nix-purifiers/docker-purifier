# SPDX-License-Identifier: MIT
{ lib }:
{
  src,
  lockFile ? src + "/docker-purifier.lock.json",
  dockerfile ? src + "/Dockerfile",
}:
let
  fix = message: "docker-purifier: ${message}; run docker-purifier lock";
  exists = builtins.pathExists lockFile && builtins.pathExists dockerfile;
  data =
    if exists then
      builtins.addErrorContext (fix "cannot parse lock") (builtins.fromJSON (builtins.readFile lockFile))
    else
      { };
  images = data.images or { };
  platforms = {
    "linux/amd64" = "x86_64-linux";
    "linux/arm64" = "aarch64-linux";
  };
  refs =
    if exists then import ./dockerfile.nix { inherit lib; } (builtins.readFile dockerfile) else [ ];
  alias = ref: builtins.substring 0 20 (builtins.hashString "sha256" ref);
  validDigest =
    digest: builtins.isString digest && builtins.match "sha256:[0-9a-f]{64}" digest != null;
  repository =
    ref:
    let
      noDigest = builtins.head (lib.splitString "@" ref);
      parts = lib.splitString "/" noDigest;
      leaf = builtins.head (lib.splitString ":" (lib.last parts));
      clean = lib.concatStringsSep "/" ((lib.init parts) ++ [ leaf ]);
      first = builtins.head parts;
      full =
        if
          builtins.length parts == 1
          || !(lib.hasInfix "." first || lib.hasInfix ":" first || first == "localhost")
        then
          "docker.io/${clean}"
        else
          clean;
      split = lib.splitString "/" full;
      host = builtins.head split;
      path = lib.concatStringsSep "/" (lib.drop 1 split);
    in
    if
      builtins.elem host [
        "docker.io"
        "index.docker.io"
        "registry-1.docker.io"
      ]
    then
      {
        registry = "registry-1.docker.io";
        path = if lib.hasInfix "/" path then path else "library/${path}";
      }
    else
      {
        registry = host;
        inherit path;
      };
  safePath =
    path:
    builtins.isString path
    && !lib.hasPrefix "/" path
    && !(builtins.elem ".." (lib.splitString "/" path));
  expectedInputFiles =
    if exists then
      [ data.dockerfile or "Dockerfile" ]
      ++ lib.optional (builtins.pathExists (src + "/.dockerignore")) ".dockerignore"
      ++ lib.optional (builtins.pathExists (dockerfile + ".dockerignore")) (
        (data.dockerfile or "Dockerfile") + ".dockerignore"
      )
    else
      [ ];
  expectedInputs = builtins.listToAttrs (
    map (name: {
      inherit name;
      value = builtins.hashFile "sha256" (
        if name == (data.dockerfile or "Dockerfile") then
          dockerfile
        else if
          name == ((data.dockerfile or "Dockerfile") + ".dockerignore")
          && builtins.pathExists (dockerfile + ".dockerignore")
        then
          dockerfile + ".dockerignore"
        else
          src + "/${name}"
      );
    }) expectedInputFiles
  );
  imageValidUnsafe =
    ref:
    let
      image = images.${ref};
    in
    builtins.match "[A-Za-z0-9_.:/@-]+" ref != null
    && !lib.hasInfix ".." ref
    && builtins.isAttrs image
    && validDigest (image.sourceDigest or null)
    && builtins.isAttrs (image.platforms or null)
    && builtins.attrNames image.platforms == lib.sort builtins.lessThan data.platforms
    && builtins.all (
      platform:
      let
        spec = image.platforms.${platform};
        manifest = builtins.fromJSON spec.manifest;
        config = builtins.fromJSON spec.config;
      in
      builtins.hasAttr platform platforms
      && builtins.isAttrs spec
      && spec.digest == "sha256:${builtins.hashString "sha256" spec.manifest}"
      && (manifest.schemaVersion or null) == 2
      && builtins.isList (manifest.layers or null)
      && manifest.config.digest == "sha256:${builtins.hashString "sha256" spec.config}"
      && (config.os or null) == "linux"
      && (config.architecture or null) == lib.last (lib.splitString "/" platform)
      && builtins.elem (config.config.OnBuild or [ ]) [
        null
        [ ]
      ]
      && builtins.all (
        object:
        builtins.isAttrs object
        && validDigest (object.digest or null)
        && builtins.isInt (object.size or null)
        && object.size >= 0
        && (object.urls or [ ]) == [ ]
      ) ([ manifest.config ] ++ manifest.layers)
    ) (builtins.attrNames image.platforms);
  imageValid =
    ref: builtins.addErrorContext (fix "invalid OCI metadata for ${ref}") (imageValidUnsafe ref);
  problems = map fix (
    if !exists then
      [ "missing lock or Dockerfile" ]
    else if !builtins.isAttrs data || (data.version or null) != 1 then
      [ "unsupported lock format" ]
    else if
      (data.contentHash or null)
      != builtins.hashString "sha256" (builtins.toJSON (removeAttrs data [ "contentHash" ]))
    then
      [ "contentHash mismatch" ]
    else if
      !builtins.isAttrs images
      || !builtins.isList (data.platforms or null)
      || data.platforms == [ ]
      || !(builtins.all (
        platform: builtins.isString platform && builtins.hasAttr platform platforms
      ) data.platforms)
      || builtins.length data.platforms != builtins.length (lib.unique data.platforms)
      || !safePath (data.dockerfile or null)
    then
      [ "invalid image metadata" ]
    else if builtins.attrNames images != refs then
      [ "missing or unexpected image entry" ]
    else if !builtins.all imageValid refs then
      [ "invalid image or missing platform" ]
    else if (data.inputs or null) != expectedInputs then
      [ "Dockerfile or ignore rules changed" ]
    else
      [ ]
  );
  entries = lib.concatMap (
    ref:
    lib.concatMap (
      platform:
      let
        image = images.${ref}.platforms.${platform};
        manifest = builtins.fromJSON image.manifest;
        prefix = "${alias ref}/${platforms.${platform}}";
        origin = repository ref;
        path = digest: "${prefix}/blobs/sha256/${lib.removePrefix "sha256:" digest}";
        metadata = [
          {
            path = "${prefix}/oci-layout";
            contents = builtins.toJSON { imageLayoutVersion = "1.0.0"; };
          }
          {
            path = "${prefix}/index.json";
            contents = builtins.toJSON {
              schemaVersion = 2;
              manifests = [
                {
                  mediaType = manifest.mediaType or "application/vnd.oci.image.manifest.v1+json";
                  digest = image.digest;
                  size = builtins.stringLength image.manifest;
                  annotations."org.opencontainers.image.ref.name" = "purifier";
                }
              ];
            };
          }
          {
            path = path image.digest;
            contents = image.manifest;
          }
          {
            path = path manifest.config.digest;
            contents = image.config;
          }
        ];
        layers = map (object: {
          path = path object.digest;
          url = "oci+https://${origin.registry}/v2/${origin.path}/blobs/${object.digest}";
          mirrors = [ ];
          hash = builtins.convertHash {
            hash = lib.removePrefix "sha256:" object.digest;
            hashAlgo = "sha256";
            toHashFormat = "sri";
          };
        }) (lib.unique manifest.layers);
      in
      map (entry: entry // { systems = [ platforms.${platform} ]; }) (metadata ++ layers)
    ) (builtins.attrNames images.${ref}.platforms)
  ) (builtins.attrNames images);
in
{
  purifier = "docker-purifier";
  inherit problems;
  dockerfile = data.dockerfile or "Dockerfile";
  outputs.image = { };
  entries = if problems == [ ] then entries else [ ];
  images = if problems == [ ] then images else { };
  platforms = data.platforms or [ ];
}
