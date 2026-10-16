{ config, lib, ... }:

{
  # Desktop configuration
  # Live-editable configurations stored in the NixOS repository.

  xdg.configFile = lib.genAttrs [
    "quickshell"
    "hypr"
    "dunst"
    "kitty"
    "fuzzel"
    "matugen"
    "rofi"
  ] (name: {
    source = config.lib.file.mkOutOfStoreSymlink
      "${config.home.homeDirectory}/nixos/dotfiles/${name}";
  });
}
