  { config, lib, pkgs, inputs, ... }:

  let
  quickshellWithWebp = pkgs.quickshell.overrideAttrs (old: {
  buildInputs = (old.buildInputs or []) ++ [
  pkgs.qt6Packages.qtimageformats

  ];
  });
  unstable = inputs.nixpkgs-unstable.legacyPackages.${pkgs.system};
  in

  {
  imports =
  [
  ./hardware-configuration.nix
  ./modules/nixos/boot.nix
  ./modules/nixos/graphics.nix
  ./modules/nixos/power.nix
  ];

  #Nix shit
  nix.settings.experimental-features = [ "nix-command" "flakes"];
  nixpkgs.config.allowUnfree = true;

  #Bullshit tools to make node/npm behave
  programs.nix-ld = {
  enable = true;
  };

  #Networking
  networking.hostName = "nixos-btw";
  networking.networkmanager.enable = true;

  # Proton VPN CLI

  networking.firewall.checkReversePath = false;
  services.dbus.enable = true;
  services.gnome.gnome-keyring.enable = true;


  # SSH
  services.openssh.enable = true;

  networking.firewall.allowedTCPPorts = [ 22 ];

  #Tailscale
  services.tailscale = {
    enable = true;
    package = inputs.nixpkgs-unstable.legacyPackages.${pkgs.system}.tailscale;
  };



  #Basic configuration
  time.timeZone = "Asia/Taipei";
  i18n.defaultLocale = "en_US.UTF-8";
  console.keyMap = "no";

  #Make my bloody trackpad work normally and maybe alittle xtra...
  services.xserver = {
  enable = true;
  libinput = {
  enable = true;
  naturalScrolling = true;
  #touchpad.tapping = true;
  #touchpad.tappingButtonMap = "lmr";
  };

  # Swap X11 mouse buttons 6 and 7 to flip horizontal scrolling back
  displayManager.sessionCommands = ''
    ${pkgs.xorg.xmodmap}/bin/xmodmap -e "pointer = 1 2 3 4 5 7 6 8 9 10 11 12"
  '';

  };

  #Window managers
  programs.hyprland = {
  enable = true;

  withUWSM = true;

  };

  # Keep Plasma removed

  services.desktopManager.plasma6.enable = false;

  #Display manager

  # Minimal TTY greeter instead of SDDM.

  services.displayManager.sddm.enable = false;

  # Only expose the UWSM Hyprland session to tuigreet.

  environment.etc."mihao/wayland-sessions/hyprland-uwsm.desktop".text = ''
  [Desktop Entry]
  Name=Hyprland (uwsm-managed)
  Comment=Hyprland launched through UWSM
  Exec=${pkgs.uwsm}/bin/uwsm start -e -D Hyprland hyprland.desktop
  TryExec=${pkgs.uwsm}/bin/uwsm
  Type=Application
  DesktopNames=Hyprland
  '';

  services.greetd = {
  enable = true;

  settings = {
    default_session = {
      command = "${pkgs.greetd.tuigreet}/bin/tuigreet --time --asterisks
      --sessions /etc/mihao/wayland-sessions --cmd \"${pkgs.uwsm}/bin/uwsm start -e
      -D Hyprland hyprland.desktop\"";
      user = "greeter";
    };
  };

  };

  #Bluetooth
  hardware.bluetooth = {
  enable = true;
  powerOnBoot = true;
  };

  #Virutalization
  virtualisation.libvirtd = {
  enable = true;

  qemu = {
    # Smaller QEMU build specialized for your host architecture.
    package = pkgs.qemu_kvm;

    # Makes shared folders available later if needed.
    vhostUserPackages = with pkgs; [
      virtiofsd
    ];
  };

  };

  programs.virt-manager.enable = true;

  # Enables convenient USB redirection into VMs.

  virtualisation.spiceUSBRedirection.enable = true;



  users.users.mihao = {
  isNormalUser = true;
  description = "Michal";
  extraGroups = [ "networkmanager" "wheel" "libvirtd" "kvm" "uinput" "input"];
  #"uinput" "input" for remote control
  };

  #PATH
  environment.localBinInPath = true;

  #Environment variables
  environment.variables = {
  NIXOS_OZONE_WL = "1"; #use ozone wayland backend
  #Force chromium
  MOZ_ENABLE_WAYLAND = "1"; #Make the bloody pinchzoom work normally

  LIBVA_DRIVER_NAME = "iHD";

  };


  #Keyaboard
  services.kanata = {
    enable = true;

    keyboards.default = {
      config = ''
        (defsrc
          caps h j k l
        )

        (defalias
          capnav (tap-hold-press 200 200 esc (layer-while-held navigation))
        )

        (deflayer base
          @capnav _ _ _ _
        )

        (deflayer navigation
          _ left down up rght
        )
      '';
    };
  };







  services.clamav.updater.enable = true;

  # KWALLET STUFF
  security.pam.services.greetd.kwallet = {
      enable = true;
      forceRun = true;
    };

    services.dbus.packages = with pkgs.kdePackages; [
      kwallet
    ];



  #Environment system packages
  environment.systemPackages = with pkgs; [
  kdePackages.dolphin
  kdePackages.kio-extras
  kdePackages.kwallet
  kdePackages.kwalletmanager
  kdePackages.kio
  kdePackages.kio-fuse
  kdePackages.qtsvg

  #For raw:
  kdePackages.gwenview
  darktable
  rawtherapee
  libraw

  #Virtualization
  dnsmasq
  p7zip

  git
  (import ./gitlarp { inherit pkgs; })
  vim-full
  neovim
  glow
  wget #World Wide Web Get
  curl
  jq #json
  iw #Network CLI configuration utility
  wev #Key
  evtest #Key
  grim #screenshot utility
  slurp #select region
  wl-clipboard #Clipboard
  playerctl
  pavucontrol

  kitty
  #waybar
  fuzzel
  dunst
  libnotify
  swayimg
  yazi

  mpv
  nomacs
  yt-dlp
  ffmpeg

  awww
  quickshellWithWebp
  matugen

  asusctl
  supergfxctl
  #rog-control-center
  brightnessctl
  psmisc #what drains power
  powertop
  powerstat
  power-profiles-daemon
  dmidecode
  libva-utils
  intel-gpu-tools
  htop
  mission-center

  hyprpicker

  btop
  fastfetch
  unzip

  #Networking:
  proton-vpn-cli
  wireguard-tools

  #software
  obsidian
  firefox
  discord
  unstable.signal-desktop
  inputs.spotatui.packages.${pkgs.stdenv.hostPlatform.system}.default
  easyeffects
  yacreader

  python3

  inputs.nixpkgs-unstable.legacyPackages.${pkgs.stdenv.hostPlatform.system}.codex
  claude-code
  chatgpt-cli
  (import inputs.nixpkgs-unstable {
    system = pkgs.stdenv.hostPlatform.system;
    config.allowUnfree = true;
  }).ollama-cuda
  ];



  # Easyeffects setup
  programs.dconf.enable = true;





  hardware.uinput.enable = true; #For remote control
  services.sunshine = {
    enable = true;
    autoStart = false;
    capSysAdmin = true;
    openFirewall = true;
  };



  programs.obs-studio = {
    enable = true;

    # Makes OBS usable as a webcam
    enableVirtualCamera = true;

    plugins = with pkgs.obs-studio-plugins; [
      obs-pipewire-audio-capture
      obs-backgroundremoval

      # Cool extras:
      obs-move-transition
      obs-shaderfilter

      # Game Capture for Vulkan/OpenGL games
      obs-vkcapture
    ];
  };


  services.jellyfin = {
    enable = true;
  };




  #Fonts
  fonts.packages = with pkgs; [
  nerd-fonts.jetbrains-mono #maple-mono.NF
  inter
  noto-fonts
  noto-fonts-cjk-sans
  font-awesome
  maple-mono.NF-unhinted
  ];



  #Image opener
  xdg.mime.defaultApplications = {
  "image/jpeg" = [ "swayimg.desktop" ];
  "image/png" = [ "swayimg.desktop" ];
  "image/gif" = [ "swayimg.desktop" ];
  "image/webp" = [ "swayimg.desktop" ];
  "image/bmp" = [ "swayimg.desktop" ];
  "image/tiff" = [ "swayimg.desktop" ];
  };



  #The nice line at the end of the file
  system.stateVersion = "26.05";
  }
