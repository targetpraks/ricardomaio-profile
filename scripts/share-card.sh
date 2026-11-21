#!/bin/bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
card="$root/assets/share-card.html"
chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

if [[ ! -f "$card" ]]; then
    echo "ERROR: missing share card: $card" >&2
    exit 2
fi
if [[ ! -x "$chrome" ]]; then
    echo "ERROR: Chrome binary not found: $chrome" >&2
    exit 2
fi
mkdir -p "$root/dist"
profile="$(mktemp -d "$root/dist/.chrome-profile.XXXXXX")"
trap 'rm -rf -- "$profile"' EXIT
card_url="$(python3 -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).as_uri())' "$card")"
rm -f -- "$root/dist/og.png"
"$chrome" --headless=new --hide-scrollbars --window-size=1200,630 \
    --user-data-dir="$profile" --no-first-run --no-default-browser-check \
    --screenshot="$root/dist/og.png" "$card_url"
python3 - "$root/dist/og.png" <<'PY'
import pathlib, struct, sys
path = pathlib.Path(sys.argv[1])
try:
    header = path.read_bytes()[:24]
    if (len(header) != 24 or header[:8] != b'\x89PNG\r\n\x1a\n'
            or header[12:16] != b'IHDR' or struct.unpack('>II', header[16:24]) != (1200, 630)):
        raise ValueError('expected a 1200x630 PNG')
except (OSError, ValueError) as error:
    print(f'ERROR: invalid share card output: {error}', file=sys.stderr)
    sys.exit(2)
print(f'WROTE: dist/og.png {path.stat().st_size} bytes (1200x630)')
PY
