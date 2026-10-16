{ config, pkgs, ... }:

{
  # NIXYNC
  # Live-editable NixOS configuration synchronization script.
  home.file.".local/bin/nixync".source =
    config.lib.file.mkOutOfStoreSymlink
      "${config.home.homeDirectory}/nixos/scripts/nixync";

  # Scan files for secrets before public GitHub pushes.
  home.packages = [
    pkgs.gitleaks
  ];

  # Make nixync available from any working directory.
  home.sessionPath = [
    "$HOME/.local/bin"
  ];
}
