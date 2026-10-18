{ pkgs ? import <nixpkgs> { } }:
pkgs.writeShellApplication {
  name = "gitlarp";
  runtimeInputs = [ pkgs.git pkgs.coreutils pkgs.python3 ];
  text = builtins.readFile ./gitlarp;
}
