{
  description = "NixOS from Scratch";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixos-unstable";

    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nixos-hardware = {
      url = "github:NixOS/nixos-hardware";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    spicetify-nix.url = "github:Gerg-L/spicetify-nix";


    spotatui = {
      url = "github:LargeModGames/spotatui";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    zen-browser = {
      url = "github:0xc000022070/zen-browser-flake";
      inputs.nixpkgs.follows = "nixpkgs-unstable";
      inputs.home-manager.follows = "home-manager";
    };
  };

  outputs = inputs@{
    self,
    nixpkgs,
    home-manager,
    spicetify-nix,
    nixos-hardware,
    nixpkgs-unstable,
    ...
  }: {
    nixosConfigurations.nixos-btw = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";

      specialArgs = { inherit inputs; };

      modules = [
        ./configuration.nix

        # Hardware config from nixos-hardware
        nixos-hardware.nixosModules.asus-zephyrus-gu605cw

        home-manager.nixosModules.home-manager

        {
          home-manager = {
            useGlobalPkgs = true;
            useUserPackages = true;
            backupFileExtension = "backup";

            # Lets /etc/nixos/home.nix access flake inputs
            extraSpecialArgs = { inherit inputs; };

            # Import Home Manager modules here.
            sharedModules = [
              inputs.spicetify-nix.homeManagerModules.default
            ];

            users.mihao = import ./home.nix;
          };
        }
      ];
    };
  };
}
