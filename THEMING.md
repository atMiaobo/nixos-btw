# Dynamic desktop themes

The canonical engine is `scripts/theming/`. The CLI and Quickshell picker share
its per-wallpaper TOML definitions. See [RECOVERY.md](RECOVERY.md) for the
ownership failure, preservation evidence, deployment gates and rollback.

## Ownership and color layers

Home Manager retains the original whole-directory out-of-store links for
Quickshell, Hyprland, Kitty, Fuzzel, Dunst, Matugen and Rofi. It never owns
individual files inside those directories. No `force` or recursive linking is
used for these apps.

One separate Home Manager target, `~/.local/share/mihao-theme`, points to
`${config.xdg.cacheHome}/theme/generated`. This fixed HOME-relative bridge lets
native includes find a configurable cache without modifying repository files.

| App | Consumed color layer | Preserved configuration |
| --- | --- | --- |
| Kitty | Final `include ~/.local/share/mihao-theme/kitty.conf`, after the native theme block | Original preferences and native theme block retained. Presets are dumped, filtered to colors and validated without editing the main config. |
| Fuzzel | `include=~/.local/share/mihao-theme/fuzzel.ini` | Original `fuzzel.ini`, with only its color include changed. Absolute or `~/` include paths are required. |
| Dunst | Existing `dunstrc.d/99-theme.conf` becomes a relative symlink to the bridge's `dunst.conf` | Original `dunstrc` is byte-identical to Git HEAD, including notification rules. |
| Hyprland | Original `require("theme")` reads the updated `theme.lua`, which falls back to the original palette and loads cached borders | Both main configs are byte-identical to HEAD. Runtime `hyprctl eval` updates only active/inactive border colors through `hl.config`; it never reloads the compositor. |
| Quickshell | `${MIHAO_THEME_CACHE}/active.json` | Common root entrypoints `dashboard.qml` and `theme-picker.qml`, `import qs.shared`, and one `shared/ThemeStore.qml`. |

Dunst's relative link assumes the original `~/nixos/dotfiles/dunst/dunstrc.d`
repository layout. Its four parent traversals reach HOME, then
`.local/share/mihao-theme/dunst.conf`. It never points into an app directory or
back into a Home Manager generation. Changing the repository layout requires
changing that link and testing it again.

For the first deployment there is **no Home Manager initialization hook**.
Initialization is an explicit manual command, kept manual until integration is
verified. Invoke the reviewed checkout directly, with Kitty available on PATH
and the intended XDG/cache paths. Do not use `~/.local/bin/theme` while reviewing
this isolated worktree: the preserved script links still refer to `~/nixos`.
For example, after the non-activating build and a separate deployment review:

```sh
python3 /home/mihao/nixos-theme-repair/scripts/bin/theme init
```

This is a future manual command, not part of the build or this review. `theme
init` creates missing runtime files or restores missing outputs from snapshots;
it does not change the wallpaper, signal applications or replace app configs.
Existing cache files are retained, except that init removes the old generator's
unsupported urgency-level Dunst `separator_color` entries. The valid global
separator and other colors are retained. Old caches must pass the staged
validation in RECOVERY.md; initialization is not general cache validation.

Before initialization, Fuzzel refuses to start if its generated include is
missing. Kitty logs the missing include and keeps its non-color preferences
with default colors. Dunst retains its main configuration and warns about the
missing drop-in; Hyprland and Quickshell use their fallback palettes. The
engine's native include checks report missing outputs as errors. None of these
paths reconstruct or overwrite application configurations.

The original Hyprland startup commands are retained, including its original
wallpaper command. Session restoration remains an explicit `theme restore-session`
command; the repair does not install a new startup hook.

## Data and environment

| Purpose | Default path |
| --- | --- |
| Wallpaper registry | `~/.config/themes/wallpapers` |
| Per-wallpaper generated TOMLs | `~/.config/themes/generated/<sha256-of-image-path>.toml` |
| Existing legacy presets | `~/.config/themes/presets/*.toml` |
| Quickshell palette | `~/.cache/theme/active.json` |
| App color outputs | `~/.cache/theme/generated/` |
| Selection, temporary overrides, runtime snapshots and lock | `~/.local/state/mihao/theme/` |

The engine honors `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_STATE_HOME`,
`MIHAO_THEME_CACHE`, `MIHAO_THEME_STATE`, `MIHAO_THEME_REGISTRY` and
`MIHAO_THEME_GENERATED_DIR`. Home Manager sets `MIHAO_THEME_CACHE` from its cache
home; use the same value in any manual shell invocation. Changing only that
variable without updating the bridge is detected as a deployment failure.

Registry rows remain unchanged:

```text
Mononoke|/home/mihao/Pictures/Wallpapers/mononoke.png
Custom|/path/to/image.png|./presets/custom.toml
```

An explicit third field is authoritative: missing or invalid files fail instead
of falling back to generated colors. Relative theme paths resolve beside the
registry. Without a third field, the normalized absolute wallpaper path selects
one stable generated TOML. Spaces are supported; shell expressions are never
executed. Duplicate names need an unambiguous path/registry identity.

## Theme definitions

[`default.toml`](scripts/theming/default.toml) is a complete schema 1 example.
All semantic UI, terminal and ANSI colors are required and use `#RRGGBB`.
The supported sections are `[meta]`, `[ui]`, `[terminal]`, `[ansi]` and optional
`[apps.APP]`. Legacy `[theme]/[palette]/[roles]` definitions remain readable.

Examples of app-specific definitions:

```toml
[apps.kitty]
source = "preset"
name = "Tokyo Night"

[apps.fuzzel]
source = "file"
path = "./launcher-colors.ini"

[apps.dunst]
source = "partial"
colors = { "urgency_critical.frame_color" = "#ff6677" }

[apps.hyprland]
source = "universal"

[apps.hyprland.active_border]
colors = ["primary", "secondary"]
angle = 45
```

Kitty supports native presets, custom color files, partial colors and universal
colors. Other adapters support universal, partial and app-specific color files.
Kitty-only native presets are rejected for other apps. Fuzzel files may contain
only `[colors]` with RRGGBBAA values. Dunst accepts only supported colors in
`global` and urgency sections; `separator_color` belongs only in `global`.
Hyprland JSON files accept only `general:col.active_border` and
`general:col.inactive_border`. Quickshell JSON overrides contain semantic UI
colors. Non-color Kitty preset/file properties are filtered with a warning;
other adapters reject non-color sections/properties.

Matugen extraction uses a temporary empty template configuration and dry-run
JSON output, so it cannot run the old configured templates. Animated WebP
extraction is isolated. Existing per-wallpaper definitions are not regenerated
on reselection. Explicit regeneration backs up the TOML and retains overrides.

Newly generated dark palettes elevate background/surface/surface-alt to minimum
Oklab lightness values of 0.30/0.36/0.42. They retain the extracted source hue at
35% of its chroma, capped at 0.05, with text contrast of at least 4.5:1 and
status/accent contrast of at least 3:1 on all three surfaces. Matugen's tonal-spot
scheme remains in use; switching schemes alone still produces near-black
neutral surfaces. Achromatic images use a neutral extraction fallback. Light
surface roles are unchanged. This transformation runs only during extraction;
saved TOMLs and explicitly configured application palettes remain authoritative.
To opt an existing wallpaper into these defaults, use `theme regenerate NAME`
(creates a backup and retains app overrides), then `theme apply NAME`.

The final Kitty include is outside `BEGIN_KITTY_THEME`/`END_KITTY_THEME`, so
native `kitten themes` edits cannot replace it. Generated files explicitly reset
supported color roles with serializable defaults to the installed Kitty version's
defaults before applying the selected palette. Sparse files and the native `Default` preset therefore
cannot inherit leftover native theme colors. Only color settings are generated.
The engine include takes precedence even on native config reloads; use the
theme CLI for temporary or saved Kitty choices. Every wallpaper selection
rewrites the generated file and verifies the effective config before requesting
SIGUSR1 reload. Saved per-wallpaper overrides take precedence over universal
colors, including on same-wallpaper reselection.

The picker displays only concise exit-code-based feedback. Full apply stdout
and stderr (including successful warnings) and registry diagnostics go to the
existing launcher log, `${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/mihao-theme-picker.log`.
That log is replaced when the picker is next launched. CLI diagnostics and
nonzero exit codes are unchanged; partial adapter failures still exit 3, and
`theme status` retains the adapter results and full failure details.

With the existing directory-owned app links and separate runtime bridge,
updating the live-linked source files needs no NixOS/Home Manager rebuild or
activation. The next picker invocation loads its updated QML; theme application
rewrites the runtime files, requests Kitty's supported reload, and updates the
dashboard through its existing JSON watcher. An isolated repair worktree does
not deploy changes to the source repository targeted by those links.

## Commands

These commands change desktop appearance when run in a real session. They were
not run against the live desktop during this repair.

```sh
theme list
theme status --json
theme apply "Mononoke"                # wallpaper + all saved app colors
theme kitty "Tokyo Night"             # temporary override
theme kitty "Tokyo Night" --save      # persist in the selected wallpaper TOML
theme kitty --file /path/colors.conf --save
theme kitty --universal --save
theme fuzzel --file /path/colors.ini
theme dunst --universal
theme hyprland --gradient 45 --save
theme quickshell --universal
theme reset kitty                    # saved Kitty appearance; no wallpaper change
theme reset                          # all saved appearances; no wallpaper change
theme regenerate "Mononoke"          # backup/regenerate definition; no live apply
theme init                           # missing runtime outputs only
theme restore-session                # selected wallpaper and runtime snapshots
```

`--save` backs up and updates the wallpaper TOML after successful rendering.
Without it, an app override is temporary. Reselecting any wallpaper, including
the current wallpaper, reapplies every saved app definition and clears temporary
overrides. `restore-session` instead retains runtime snapshots and temporary
choices. There is no background reconciliation daemon.

Rendering validates all requested plans before wallpaper work. Adapter delivery
can still fail independently. The engine restores previous generated files on
failure where possible, records partial failure and exits 3. `--save` persists
before delivery, so a failed delivery may still leave the saved definition
updated. A process can accept a request before later verification fails; global
live rollback is not guaranteed. Use `theme status` and an explicit retry/reset.

Kitty validates the effective palette using its own config loader, including
native config discovery and running instances' command-line color overrides.
Later color settings or alternate configs that hide the generated palette are
reported as failures. It requests the supported native SIGUSR1 reload for
same-user Kitty GUI processes (including Nix wrapped names), excludes helpers,
and reports signaled, skipped and disappeared PIDs. Linux's blocked/signalfd
receiver and traditional signal handlers are supported. No visible GUI means
"staged for next Kitty launch", not successful live delivery. Signal delivery
is not application acknowledgment. Inherited sockets are not used and remote
control permissions are unchanged. Fuzzel
runs its native config checker and uses colors on the next launch. Dunst uses
native drop-in discovery and requests `dunstctl reload`; explicit `-conf` daemon
launches bypass default discovery and are rejected. Hyprland verifies dotted
border options with `getoption` after the Lua update. Quickshell watches atomic
JSON replacements and retains the last valid palette on malformed JSON.
The shared ThemeStore accepts canonical UI roles and the legacy dashboard
aliases; missing aliases are derived from the current palette instead of the
fallback theme. The dashboard's primary/secondary accents use canonical roles.

## Manual appearance verification after deploying the reviewed sources

The repair worktree does not change the linked live checkout. These source-only
changes require no Home Manager rebuild or NixOS activation. Deploy the reviewed
sources separately before running the following commands in a desktop session.

Previously generated wallpapers can retain near-black dark backgrounds
(`#0e1513` through `#1a1110` were observed before this fix). Existing TOMLs are
never silently regenerated. A dark terminal/dashboard alone does not establish
a reload failure. Use visibly distinct temporary colors to check existing and
new Kitty windows, then reset to the selected wallpaper's saved definitions:

```sh
theme kitty "Belafonte Day"           # existing cached native light preset
theme status                         # effective validation and signal PID report
kitty                                # new process should have the same palette
theme reset kitty                    # restore saved appearance; no wallpaper change

probe=$(mktemp /tmp/dashboard-theme.XXXXXX.json)
cat > "$probe" <<'JSON'
{"colors":{"background":"#fff0d0","surface":"#ffe0a0","surface_alt":"#f0c080","foreground":"#102030","muted":"#405060","primary":"#b03020","secondary":"#306090","border":"#804010","success":"#207030","warning":"#906000","error":"#a02030"}}
JSON
theme quickshell --file "$probe"      # already-open dashboard should change
theme quickshell --universal          # verify a second update
theme reset quickshell                # restore any saved per-app override
rm "$probe"
```

Within Kitty, Ctrl+Shift+F6 shows the running configuration; Ctrl+Shift+F5
requests a manual native reload. If the light preset is unavailable offline,
use `theme kitty --file /path/to/colors.conf` instead. A palette-verification
failure names conflicting colors; inspect later includes, `--config`, `-o`,
and `KITTY_CONFIG_DIRECTORY`. Applications can also set their own terminal
colors via escape sequences; inspect a plain shell when checking the palette.

## Non-activating tests

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests/theming -v
```

The suite includes original-config preservation, evaluated Nix declarations,
absence of automatic initialization, explicit worktree initialization,
idempotence, missing-cache behavior, repeated fixture installation using cached HM
helpers, native application parsers, actual Quickshell imports/watching,
wallpaper reselection, temporary/saved overrides, malformed files and failure
rollback. See RECOVERY.md for exact verification boundaries.
The appearance regressions include three distinct effective Kitty palettes,
native config/CLI precedence, mocked signal delivery and targeting, and an
offscreen dashboard using its actual visual children through repeated atomic
theme replacements, canonical/legacy roles, and invalid updates. The Wayland
surface alone is replaced with Items in that test; desktop apps are untouched.
