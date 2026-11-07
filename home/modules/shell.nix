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
      # Kitty shell integration, preserving normal NixOS Bash startup
      if test -n "$KITTY_INSTALLATION_DIR" &&
         test -f "$KITTY_INSTALLATION_DIR/shell-integration/bash/kitty.bash"; then
        export KITTY_SHELL_INTEGRATION=enabled
        source "$KITTY_INSTALLATION_DIR/shell-integration/bash/kitty.bash"
      fi
    '';
  };
}
