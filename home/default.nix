{ config, ... }: {
  imports = [
    ./modules/git.nix
    ./modules/neovim.nix
    ./modules/shell.nix
    ./modules/spicetify.nix
    ./modules/media.nix
    ./modules/packages.nix
  ];

  home.username = "mihao";
  home.homeDirectory = "/home/mihao";
  home.stateVersion = "26.05";

  # Expose Home Manager session variables to UWSM
  xdg.configFile."uwsm/env".source =
    "${config.home.sessionVariablesPackage}/etc/profile.d/hm-session-vars.sh";
}
