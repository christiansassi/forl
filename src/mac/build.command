#!/bin/bash
# Build the macOS app and widget extension, then install them into /Applications.
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

# /Applications, not ~/Applications. Control Center draws a control's icon in
# its own sandboxed process, which is denied read access to an app bundle kept
# under the home folder: the icon resolves to nothing and the control comes out
# empty, with "No image named ... found in asset catalog" in the system log.
applications_dir="/Applications"
installed_app="$applications_dir/FORL.app"
if [[ ! -w "$applications_dir" ]]; then
	printf 'Cannot write to %s. Run this from an administrator account.\n' "$applications_dir" >&2
	exit 1
fi

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

# Stop the app before replacement. WidgetKit may immediately respawn its extension.
pkill -x FORL 2>/dev/null || true
for attempt in {1..50}; do
	if ! pgrep -x FORL >/dev/null; then
		break
	fi
	sleep 0.1
done
if pgrep -x FORL >/dev/null; then
	printf 'FORL is still stopping. Run the installer again after it exits.\n' >&2
	exit 1
fi
if [[ -e "$installed_app" ]]; then
	pluginkit -r "$installed_app/Contents/PlugIns/FORLWidgets.appex" || true
	mv "$installed_app" "$staging_dir/previous.app"
fi
mv "$staging_dir/FORL.app" "$installed_app"
# Restart only after the new executable is in place, so any respawn loads it.
pkill -x FORLWidgets 2>/dev/null || true
pluginkit -r "$built_app/Contents/PlugIns/FORLWidgets.appex" || true
# Remove the parent build record too: ExtensionKit can otherwise keep launching
# that executable after its plug-in record has been removed.
/System/Library/Frameworks/CoreServices.framework/Versions/Current/Frameworks/LaunchServices.framework/Versions/Current/Support/lsregister -u "$built_app"
/System/Library/Frameworks/CoreServices.framework/Versions/Current/Frameworks/LaunchServices.framework/Versions/Current/Support/lsregister -f "$installed_app"
pluginkit -a "$installed_app/Contents/PlugIns/FORLWidgets.appex"
# Drop cached extension launch paths without changing widget configurations.
pkill -u "$(id -u)" -x chronod 2>/dev/null || true
printf 'Installed %s\n' "$installed_app"
