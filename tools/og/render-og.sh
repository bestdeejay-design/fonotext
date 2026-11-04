#!/bin/bash
# Рендер OG/социальных картинок Fonotext из канонического hero (og-hero.html).
# Форматы задаются классом на body через ?fmt=; DPR 1; вывод PNG в docs/.
# Использование: bash tools/og/render-og.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
declare -A FMT=( [og]=1200,630 [square]=1080,1080 [story]=1080,1920 [vk]=1590,400 [li]=1584,396 )
declare -A OUT=( [og]="../../docs/og-image.png" [square]="../../docs/social/square-1080.png" [story]="../../docs/social/stories-1080x1920.png" [vk]="../../docs/social/vk-cover-1590x400.png" [li]="../../docs/social/linkedin-1584x396.png" )
cd "$DIR"
for k in og square story vk li; do
  "$CHROME" --headless=new --disable-gpu --screenshot="$k.png" \
    --window-size="${FMT[$k]}" --force-device-scale-factor=1 --hide-scrollbars \
    --default-background-color=00000000 "file://$DIR/og-hero.html?fmt=$k"
  sips -g pixelWidth -g pixelHeight "$k.png" | grep -q . && cp "$k.png" "${OUT[$k]}"
done
echo "Готово: docs/og-image.png + docs/social/*"
