{ config, lib, ... }:

let
  # Discover scripts dynamically from the repository.
  scriptDir = ../../scripts/bin;

  scripts = lib.filterAttrs
    (_: type: type == "regular")
    (builtins.readDir scriptDir);

in
{
  # Custom scripts
  # Expose every repository script as a global command.

  home.file = lib.mapAttrs'
    (name: _: lib.nameValuePair ".local/bin/${name}" {
      source = config.lib.file.mkOutOfStoreSymlink
        "${config.home.homeDirectory}/nixos/scripts/bin/${name}";
    })
    scripts;
}
