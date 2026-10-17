
{ pkgs, ... }:

{
  home.packages = [
    (pkgs.writeShellApplication {
      name = "claude-local";

      runtimeInputs = with pkgs; [
        claude-code
        curl
        jq
      ];

      text = ''
        set -euo pipefail

        # Separate Claude Code configuration
        export CLAUDE_CONFIG_DIR="$HOME/.claude-local"

        # Local Ollama API
        export ANTHROPIC_BASE_URL="http://127.0.0.1:11434"
        export ANTHROPIC_AUTH_TOKEN="ollama"
        export ANTHROPIC_API_KEY=""

        # Prevent inherited model/provider overrides
        unset ANTHROPIC_MODEL
        unset CLAUDE_CODE_USE_BEDROCK
        unset CLAUDE_CODE_USE_VERTEX
        unset CLAUDE_CODE_USE_FOUNDRY

        # Initial model, until /model saves a preference
        export ANTHROPIC_DEFAULT_MODEL="qwen3.5:9b"

        # Match Claude Code's context assumptions to Ollama
        export CLAUDE_CODE_MAX_CONTEXT_TOKENS="65536"

        mkdir -p "$CLAUDE_CONFIG_DIR"

        # Discover installed Ollama models
        if ! tags=$(curl -fsS --max-time 5 \
          "$ANTHROPIC_BASE_URL/api/tags"); then
          echo "Error: Ollama is not running." >&2
          exit 1
        fi

        # Build the /model picker dynamically
        picker=$(printf '%s' "$tags" | jq -c '{
          modelPicker: {
            replaceBuiltInOptions: true,
            options: [
              .models[] |
              {
                model: .name,
                label: .name,
                description: "Local Ollama model"
              }
            ]
          }
        }')

        count=$(printf '%s' "$picker" |
          jq '.modelPicker.options | length')

        if [ "$count" -eq 0 ]; then
          echo "No local models installed." >&2
          echo "Try: ollama pull qwen3.5:9b" >&2
          exit 1
        fi

        # Launch existing Claude Code with local settings
        exec claude --settings "$picker" "$@"
      '';
    })
  ];
}

