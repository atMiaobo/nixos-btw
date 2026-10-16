{ pkgs, ... }: {
  home.packages = with pkgs; [
    ripgrep
    fd
    tree
    unzip
    qbittorrent
  ];
}
