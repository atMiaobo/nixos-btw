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

  package = config.boot.kernelPackages.nvidiaPackages.latest;

  };

  # Only start NVIDIA Dynamic Boost when the GPU is available.
  # Prevent nvidia-powerd from failing in Integrated mode.
  systemd.services.nvidia-powerd.unitConfig.ConditionPathExists = "/dev/nvidia0";

}
