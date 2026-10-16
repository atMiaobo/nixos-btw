{ pkgs, ... }:

{
  #Boot options
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;
  boot.loader.systemd-boot.configurationLimit = 2;

  boot.kernelParams = [
    "i915.enable_dpcd_backlight=3"
    "resume_offset=440702976"
  ];

  # Use the newest kernel available in this nixpkgs revision.

  boot.kernelPackages = pkgs.linuxPackages_latest;

  boot.kernelPatches = [
    {
      name = "vmd-aspm-os-control";
      patch = ../../patches/vmd-aspm-os-control.patch;
    }
  ];


  swapDevices = [{
    device = "/var/lib/swapfile";
    size = 32 * 1024;
  }];

  boot.resumeDevice = "/dev/nvme0n1p7";



}
