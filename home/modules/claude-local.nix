
{ pkgs, inputs, ... }:

let
  # Use the unstable package only for claude-local.
  unstable = import inputs.nixpkgs-unstable {
    system = pkgs.stdenv.hostPlatform.system;
    config.allowUnfree = true;
  };

  localClaude = unstable.claude-code;
in
{
  home.packages = [
    (pkgs.writeShellApplication {
      name = "claude-local";

      runtimeInputs = with pkgs; [
        curl
        jq
        systemd
        coreutils
      ];

      text = ''
        set -euo pipefail

        # Allow checking the version without starting Ollama.
        if [ "$#" -eq 1 ] && [ "$1" = "--version" ]; then
          exec ${localClaude}/bin/claude --version
        fi

        # Completely separate Claude Code configuration.
        export CLAUDE_CONFIG_DIR="$HOME/.claude-local"
        mkdir -p "$CLAUDE_CONFIG_DIR"

        # Send inference requests to local Ollama.
        export ANTHROPIC_BASE_URL="http://127.0.0.1:11434"
        export ANTHROPIC_AUTH_TOKEN="ollama"
        export ANTHROPIC_API_KEY=""

        # Prevent inherited model/provider overrides.
        unset ANTHROPIC_MODEL
        unset CLAUDE_CODE_USE_BEDROCK
        unset CLAUDE_CODE_USE_VERTEX
        unset CLAUDE_CODE_USE_FOUNDRY

        # Start Ollama automatically if needed.
        if ! curl -fsS --max-time 2 \
          "$ANTHROPIC_BASE_URL/api/tags" >/dev/null 2>&1; then
          systemctl --user start ollama
        fi

        # Wait for the server to respond.
        tags=""

        for (( attempt=1; attempt<=20; attempt++ )); do
          if tags=$(curl -fsS --max-time 2 \
            "$ANTHROPIC_BASE_URL/api/tags" 2>/dev/null); then
            break
          fi
          sleep 1
        done

        if [ -z "$tags" ]; then
          echo "Error: Ollama did not start." >&2
          exit 1
        fi

        # Obtain a safe local default model.
        fallback=$(printf '%s' "$tags" |
          jq -r '.models[0].name // empty')

        if [ -z "$fallback" ]; then
          echo "No Ollama models found." >&2
          exit 1
        fi

        # A saved /model choice takes priority.
        export ANTHROPIC_DEFAULT_MODEL="$fallback"

        # Fix an old selection such as "opus" left over
        # from the previous Claude Code installation.
        settings="$CLAUDE_CONFIG_DIR/settings.json"

        if [ -f "$settings" ]; then
          saved=$(jq -r '.model // empty' "$settings")

          if [ -n "$saved" ] && \
             ! printf '%s' "$tags" | jq -e \
               --arg name "$saved" \
               'any(.models[]; .name == $name)' >/dev/null; then

            tmp=$(mktemp "$CLAUDE_CONFIG_DIR/settings.XXXXXX")
            jq --arg model "$fallback" \
              '.model = $model' "$settings" > "$tmp"

            chmod 600 "$tmp"
            mv "$tmp" "$settings"
          fi
        fi

        # Generate /model entries from installed Ollama models.
        picker=$(printf '%s' "$tags" | jq -c '{
          modelPicker: {
            replaceBuiltInOptions: true,
            options: [
              .models[] | {
                model: .name,
                label: .name,
                description: "Local Ollama model"
              }
            ]
          }
        }')

        # Start the unstable Claude Code binary.
        # Do not pass --model: let /model persist selections.
        exec ${localClaude}/bin/claude --settings "$picker" "$@"
      '';
    })
  ];
}

