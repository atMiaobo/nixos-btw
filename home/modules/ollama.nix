{ pkgs, inputs, ... }:

let
  unstable = import inputs.nixpkgs-unstable {
    system = pkgs.stdenv.hostPlatform.system;
    config.allowUnfree = true;
  };
in

{
  systemd.user.services.ollama = {
    Unit = {
      Description = "Ollama local inference server";
    };

    Service = {
      Type = "simple";
      ExecStart = "${unstable.ollama-cuda}/bin/ollama serve";
      Environment = [
        "OLLAMA_HOST=127.0.0.1:11434"
        "OLLAMA_MODELS=/home/mihao/.ollama/models"
        "OLLAMA_CONTEXT_LENGTH=32768"
        "OLLAMA_KEEP_ALIVE=1m"
        "OLLAMA_NO_CLOUD=1"
      ];

      Restart = "on-failure";
      RestartSec = 3;
    };

    # No Install.WantedBy:
    # This service starts only when explicitly requested.
  };
}

