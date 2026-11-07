
{ pkgs, inputs, ... }:

{
  programs.yazi = {
    enable = true;

    # Get Yazi from unstable Nixpkgs
    package = inputs.nixpkgs-unstable.legacyPackages.${pkgs.stdenv.hostPlatform.system}.yazi;

    settings = {
      mgr = {
        sort_by = "mtime";
        sort_reverse = true;
        sort_dir_first = true;
        linemode = "size";
      };
    };
  };
}

