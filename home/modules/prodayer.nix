{ inputs, ... }:
{
  imports = [ inputs.prodayer.homeManagerModules.default ];

  programs.prodayer = {
    enable = true;
    hyprland.enable = true;
  };
}
