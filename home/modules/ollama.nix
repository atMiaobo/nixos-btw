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

        # Context
        #"OLLAMA_CONTEXT_LENGTH=131072"
        "OLLAMA_CONTEXT_LENGTH=32768"

        # Enable memory-efficient attention
        "OLLAMA_FLASH_ATTENTION=1"

        # Quantize KV cache to 8-bit
        "OLLAMA_KV_CACHE_TYPE=q8_0"

        # Avoid multiplying context allocations
        "OLLAMA_NUM_PARALLEL=1"

        # Unload models after inactivity
        "OLLAMA_KEEP_ALIVE=1m"

        # Disable Ollama cloud functionality
        "OLLAMA_NO_CLOUD=1"
      ];

      Restart = "on-failure";
      RestartSec = 3;
    };

    # No Install.WantedBy:
    # This service starts only when explicitly requested.
  };
}

