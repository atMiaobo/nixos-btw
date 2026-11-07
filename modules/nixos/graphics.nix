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
    version = "615.78.08";

    sha256_64bit = "sha256-Pj9t3cLudnoIGFMAr3vjyyhuznZpjS3eNSRZl4LQf/4=";
    sha256_aarch64 = "sha256-UHYBE1AYHoGgMfD9AS/jX+S+N8eCDWUft6qolK9Eejc=";
    openSha256 = "sha256-HBINiOjL0ZJLIAJeNIBYHBnwgUXtNwPPtnFpAI1YwF4=";
    settingsSha256 = "sha256-inDRpG02sdDgHmlqgu/DsgK8OFdOt1fZIYyXdhlGC/c=";
    persistencedSha256 = "sha256-RzeR6Ldct6MUxjnXRyThdh5Y3jjMehTVg85MtwuWNX4=";
  };

  };

  # Only start NVIDIA Dynamic Boost when the GPU is available.
  # Prevent nvidia-powerd from failing in Integrated mode.
  systemd.services.nvidia-powerd.unitConfig.ConditionPathExists = "/dev/nvidia0";

}
