final: prev: {
  docker-purifier = {
    readLock = import ./read-lock.nix { lib = final; };
  };
}
