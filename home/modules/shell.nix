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

      # Force a fresh Wi-Fi scan before opening nmtui
        nmtui() {
          nmcli -w 20 device wifi list ifname wlo1 --rescan yes >/dev/null 2>&1
          command nmtui "$@"
        }
    '';
  };
}
