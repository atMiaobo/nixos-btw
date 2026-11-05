{ config, pkgs, ... }:

{
  #Graphics and asus shit
  services.asusd.enable = true;
  services.supergfxd.enable = true;

  services.xserver.videoDrivers = [ "nvidia" ];

  hardware.graphics = {
  enable = true;

  extraPackages = with pkgs; [
    intel-media-driver
    vpl-gpu-rt
  ];

  };

  hardware.nvidia = {
  open = true;
  modesetting.enable = true;
  nvidiaSettings = true;

  #Pathed this package = config.boot.kernelPackages.nvidiaPackages.latest; 
  package = config.boot.kernelPackages.nvidiaPackages.mkDriver {
    version = "610.57.04";
    sha256_64bit = "sha256-suk1xmuDuwDAyFe8jg7g/VLekoa0DJzB7sKafOfrEW0=";
    sha256_aarch64 = "sha256-QCefrMBCmpOwuOyXv1k5Gj0iB2CYlPgnG3JToUw/j54=";
    openSha256 = "sha256-rQHOOOY4KL92Ww3KDwh+j4eGU7oNAH8LutZC5wmFnPo=";
    settingsSha256 = "sha256-ZEMo8I8Zc2Tq6RVDNYpAH+f094dUaZiBqO+5f6lIjRI=";
    persistencedSha256 = "sha256-aXmD2VY1RLlgAnlHhOUMWzvMyhI6JTClcFLm4imF/mA=";
    patchesOpen = [ ../../patches/nvidia-open-gpio-const.patch ];
  };

  };

  # Only start NVIDIA Dynamic Boost when the GPU is available.
  # Prevent nvidia-powerd from failing in Integrated mode.
  systemd.services.nvidia-powerd.unitConfig.ConditionPathExists = "/dev/nvidia0";

}
