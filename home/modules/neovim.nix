{ config, lib, ... }:

{
  #NVIM
  programs.neovim = {
    enable = true;
    defaultEditor = true;
    viAlias = true;
    vimAlias = true;

    # Let our own init.lua control Neovim.
    sideloadInitLua = true;
  };

  # Explicitly enable link despite Neovim's sideload setting.
  xdg.configFile."nvim/init.lua".enable = lib.mkForce true;

  # Link the actual Lua configuration from our Git repo.
  # Changes to init.lua do not require rebuilding NixOS.
  xdg.configFile."nvim/init.lua".source =
    config.lib.file.mkOutOfStoreSymlink
      "${config.home.homeDirectory}/nixos/dotfiles/nvim/init.lua";
}
