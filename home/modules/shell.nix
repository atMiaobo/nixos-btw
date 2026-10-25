{ ... }: {
  #BASH
  programs.bash.enable = true;

  programs.bash.initExtra = ''
    cl() {
      cd "$@" && ls
    }
  '';
}
