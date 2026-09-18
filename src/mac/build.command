#!/bin/bash
# Build the macOS app and widget extension, then install for the current user.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
	printf 'Run this helper on macOS with the full Xcode app installed.\n' >&2
	exit 1
fi

project_dir="$(cd "$(dirname "$0")" && pwd)"
if ! xcrun --find xcodebuild >/dev/null 2>&1 || ! xcodebuild -version >/dev/null 2>&1; then
	printf 'Install Xcode, open it to finish setup, and select it in Xcode Settings > Locations > Command Line Tools.\n' >&2
	exit 1
fi

xcodebuild \
	-project "$project_dir/FORL.xcodeproj" \
	-target FORL \
	-configuration Release \
	"SYMROOT=$project_dir/.build/products" \
	"OBJROOT=$project_dir/.build/intermediates" \
	build

built_app="$project_dir/.build/products/Release/FORL.app"
test -d "$built_app/Contents/PlugIns/FORLWidgets.appex"
codesign --verify --deep --strict "$built_app"

applications_dir="$HOME/Applications"
installed_app="$applications_dir/FORL.app"
mkdir -p "$applications_dir"
staging_dir="$(mktemp -d "$applications_dir/.forl-install.XXXXXX")"

# Restore the previous app if replacement fails after it has been moved aside.
cleanup() {
	if [[ -d "$staging_dir/previous.app" && ! -e "$installed_app" ]]; then
		mv "$staging_dir/previous.app" "$installed_app"
	fi
	rm -rf -- "$staging_dir"
}
trap cleanup EXIT

ditto "$built_app" "$staging_dir/FORL.app"
codesign --verify --deep --strict "$staging_dir/FORL.app"
if [[ -e "$installed_app" ]]; then
	mv "$installed_app" "$staging_dir/previous.app"
fi
mv "$staging_dir/FORL.app" "$installed_app"
printf 'Installed %s\nOpen it from Finder to start FORL.\n' "$installed_app"
