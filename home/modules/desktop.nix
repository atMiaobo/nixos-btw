{ config, lib, ... }:

let
  themeCache = "${config.xdg.cacheHome}/theme";
in
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

  # One disjoint bridge: native app includes (and Dunst's drop-in symlink)
  # can reach a configurable cache without installing files through dotfiles.
  home.file.".local/share/mihao-theme".source =
    config.lib.file.mkOutOfStoreSymlink "${themeCache}/generated";

  home.sessionVariables.MIHAO_THEME_CACHE = themeCache;

  # First deployment: initialize explicitly from the reviewed checkout.
  # Do not run theme scripts or write runtime state during HM activation.
}
