{ lib, ... }:

{
  # POWER OPTIMIZATION TEST
  # Let power-profiles-daemon own the general power policy.
  services.tuned.enable = lib.mkForce false;
  services.tlp.enable = lib.mkForce false;
  services.power-profiles-daemon.enable = lib.mkForce true;

  # Intel thermal management is fine alongside PPD.
  services.thermald.enable = true;

  # Generic device-level auto tuning.
  powerManagement.powertop.enable = true;




}
