#!/usr/bin/env bash
# Render the landing page's system-design diagrams from docs/DIAGRAMS.md.
#
# docs/DIAGRAMS.md is the source of truth: each `## `<id>`` heading owns one
# mermaid block, and this renders each to frontend/public/diagrams/<id>.svg.
# Output is committed, so the landing page ships no runtime mermaid dependency.
#
#   ./tools/render_diagrams.sh              # all of them
#   ./tools/render_diagrams.sh orch svc      # just these, leaving the rest alone
#   ./tools/render_diagrams.sh --stamp-only  # re-stamp sizes, render nothing
#
# --stamp-only is for SVGs exported by hand from the Mermaid live editor and
# dropped into frontend/public/diagrams/. Those come out with width="100%" and no
# height, which leaves the file with no intrinsic size — the <img> then cannot
# reserve its box and the diagram fills its container instead of holding its own
# size. Stamping fixes that without touching a single drawn pixel.
#
# Needs network on first run: mermaid-cli and its headless Chrome are pulled
# into a throwaway directory rather than added to frontend/package.json, since
# nothing in the app bundle uses them.
#
# The version is PINNED so the renderer itself stops being a moving target.
#
# It does NOT make output reproducible. `overview` and `svc` render different
# bezier coordinates on EVERY run, even at a fixed version — measured: two
# consecutive runs of 11.16.0 differ by ~42KB across those two files, while the
# other five are byte-identical. Same source, same width/height, nothing visibly
# different. Mermaid's layout breaks ties nondeterministically and those two
# diagrams are dense enough to hit it.
#
# So: re-render only what actually changed (`./tools/render_diagrams.sh svc`),
# and if `overview`/`svc` come back dirty with no edit to docs/DIAGRAMS.md,
# `git checkout --` them. Committing that churn buys nothing.
# ponytail: living with it. Rounding coordinates post-render would fix it, but
# that is a bespoke SVG rewriter to silence a cosmetic diff.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/frontend/public/diagrams"
CFG="$ROOT/mermaid.config.json"
WORK="${TMPDIR:-/tmp}/kairos-diagrams"
MERMAID_CLI_VERSION="11.16.0"

STAMP_ONLY=0
if [ "${1:-}" = "--stamp-only" ]; then STAMP_ONLY=1; shift; fi
WANTED="$*"   # empty means all

mkdir -p "$OUT" "$WORK"
cd "$WORK"
if [ "$STAMP_ONLY" = "0" ]; then
  [ -d node_modules/@mermaid-js ] || npm install --silent "@mermaid-js/mermaid-cli@$MERMAID_CLI_VERSION"
fi

# Split docs/DIAGRAMS.md into one .mmd per diagram id.
node -e '
const fs = require("fs");
const md = fs.readFileSync(process.argv[1], "utf8");
const ids = [];
for (const m of md.matchAll(/^## `([a-z]+)`[^\n]*\n([\s\S]*?)(?=^## |$(?![\s\S]))/gm)) {
  const block = /```mermaid\n([\s\S]*?)\n```/.exec(m[2]);
  if (!block) continue;
  fs.writeFileSync(m[1] + ".mmd", block[1] + "\n");
  ids.push(m[1]);
}
if (!ids.length) { console.error("no mermaid blocks found"); process.exit(1); }
fs.writeFileSync("ids.txt", ids.join("\n") + "\n");  // trailing newline: `read` drops a final unterminated line
' "$ROOT/docs/DIAGRAMS.md"

while read -r id; do
  if [ -n "$WANTED" ] && ! printf '%s\n' $WANTED | grep -qx "$id"; then continue; fi
  [ "$STAMP_ONLY" = "1" ] && continue
  # -b white is load-bearing: without it mermaid emits a transparent SVG and the
  # parts classDef does not reach (clusters, edge labels, arrowheads) resolve
  # against the wrong ground. The panel that shows these is white.
  ./node_modules/.bin/mmdc -i "$id.mmd" -o "$OUT/$id.svg" -c "$CFG" -b white >/dev/null
  echo "rendered $id"
done < ids.txt

# mermaid-cli emits width="100%", which leaves the file with no intrinsic size —
# an <img> then cannot reserve its box before the SVG loads, and `max-w-full`
# reads as "fill the container", upscaling the small diagrams. Stamp the
# viewBox's own pixel size back on so each diagram renders at its natural size.
node -e '
const fs = require("fs");
const wanted = process.argv[2] ? process.argv[2].split(/\s+/) : null;
for (const id of fs.readFileSync("ids.txt", "utf8").trim().split("\n")) {
  if (wanted && !wanted.includes(id)) continue;
  const path = process.argv[1] + "/" + id + ".svg";
  if (!fs.existsSync(path)) { console.log(`${id}  (no svg, skipped)`); continue; }
  let s = fs.readFileSync(path, "utf8");
  const vb = /viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"/.exec(s);
  const w = Math.round(+vb[1]), h = Math.round(+vb[2]);
  // Matches whatever svg id the exporter used ("my-svg" from mermaid-cli,
  // "export-svg" from the live editor), and is a no-op once already stamped.
  s = s.replace(/^<svg id="([^"]*)" width="100%"( height="[^"]*")?/, `<svg id="$1" width="${w}" height="${h}"`)
       .replace(/style="max-width: *[\d.]+px; *background(-color)?: *[^;"]*;?"/, `style="background-color:#ffffff"`);
  fs.writeFileSync(path, s);
  console.log(`${id}  ${w}x${h}`);
}
' "$OUT" "$WANTED"

echo "→ $OUT"
