#!/bin/bash
# Cut the shared app icon into the sizes the macOS app catalog needs.
#
# The icon lives once, at src/common/assets/icon.png, so that the Mac app and the
# Windows executable are built from the same artwork. That file is a 1024 by 1024
# PNG with an alpha channel; every size below is derived from it here, at build
# time, rather than kept in the repository as ten near-copies of one drawing.
#
# A missing source leaves whatever the catalog already holds, so a checkout with
# no icon of its own still builds, and the catalog index is written either way so
# that the build phase always produces the file it says it does.
set -euo pipefail

source_icon="$1"
iconset="$2"

mkdir -p "$iconset"

# The sizes the catalog names, each written at 1x and again at 2x.
sizes=(16 32 128 256 512)
entries=""
for size in "${sizes[@]}"; do
	if [[ -f "$source_icon" ]]; then
		sips --resampleHeightWidth "$size" "$size" "$source_icon" --out "$iconset/icon_${size}x${size}.png" >/dev/null
		sips --resampleHeightWidth "$((size * 2))" "$((size * 2))" "$source_icon" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
	fi
	entries+="		{
			\"filename\": \"icon_${size}x${size}.png\",
			\"idiom\": \"mac\",
			\"scale\": \"1x\",
			\"size\": \"${size}x${size}\"
		},
		{
			\"filename\": \"icon_${size}x${size}@2x.png\",
			\"idiom\": \"mac\",
			\"scale\": \"2x\",
			\"size\": \"${size}x${size}\"
		},
"
done

cat > "$iconset/Contents.json" <<CONTENTS
{
	"images": [
${entries%,
}
	],
	"info": {
		"author": "xcode",
		"version": 1
	}
}
CONTENTS
