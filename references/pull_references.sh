#!/usr/bin/env bash
# Pull reference materials (rulebooks, style guides) for DeckSage UI/UX work.
# Run from repo root: ./references/pull_references.sh
#
# These PDFs are gitignored (references/ in .gitignore).
# Some URLs may require a browser download (Cloudflare-protected).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$SCRIPT_DIR/rulebooks"
mkdir -p "$OUT"

# source_url -> local_filename
declare -A REFS=(
  ["https://img.yugioh-card.com/en/downloads/rulebook/SD_RuleBook_EN_10.pdf"]="yugioh_rulebook.pdf"
  ["https://media.wizards.com/2026/downloads/MagicCompRules%2020260227.pdf"]="magic_comp_rules_2026.pdf"
  ["https://officialgamerules.org/wp-content/uploads/2025/02/Magic-The-Gathering-Rulebook.pdf"]="magic_basic_rulebook.pdf"
  ["https://tcg.pokemon.com/assets/img/learn-to-play/getting-started/quick-start-rules/en-us/quick_start_rulebook.pdf"]="pokemon_quick_start.pdf"
)

ok=0
fail=0

for url in "${!REFS[@]}"; do
  fname="${REFS[$url]}"
  dest="$OUT/$fname"

  if [[ -f "$dest" ]] && file "$dest" | grep -q "PDF document"; then
    echo "SKIP  $fname (already exists)"
    ((ok++))
    continue
  fi

  echo -n "PULL  $fname ... "
  # Use full browser headers to bypass Cloudflare challenges (e.g. pokemon.com)
  if curl -fsSL --max-time 60 --compressed \
    -H "Accept: application/pdf,*/*" \
    -H "Accept-Language: en-US,en;q=0.9" \
    -H "Sec-Fetch-Dest: document" \
    -H "Sec-Fetch-Mode: navigate" \
    -H "Sec-Fetch-Site: none" \
    -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" \
    -o "$dest" "$url" 2>/dev/null && file "$dest" | grep -q "PDF document"; then
    size=$(wc -c < "$dest" | tr -d ' ')
    echo "OK (${size} bytes)"
    ((ok++))
  else
    rm -f "$dest"
    echo "FAILED (may need browser download)"
    echo "  URL: $url"
    ((fail++))
  fi
done

echo ""
echo "Done: $ok OK, $fail failed"
if [[ $fail -gt 0 ]]; then
  echo "For failed downloads, open the URL in a browser and save to $OUT/"
fi
