{ ... }: {
  programs.bash = {
    enable = true;

    # ALIASES
    shellAliases = {
      ".." = "cd ..";
      "..." = "cd ../..";
      "...." = "cd ../../..";
    };

    # FUNCTIONS
    initExtra = ''
      cl() {
        cd "$@" && ls
      }
    '';
  };
}
