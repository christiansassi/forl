/*
 * Palette, type ramp and the colors derived from them, as the panel has them.
 *
 * Every value here is the one src/common/render/theme.py gives the Windows and
 * Linux panel, so the menu this extension opens is set in the same colors and
 * the same sizes. Change a value there and change it here.
 */

import Gio from 'gi://Gio';

// Stops of the usage ramp as [percentage, [red, green, blue]]. A value between
// two stops is mixed from them, so a bar shifts continuously rather than
// jumping at a threshold.
const USAGE_RAMP = [
	[0, [48, 209, 88]],
	[50, [227, 193, 59]],
	[75, [232, 145, 45]],
	[100, [255, 69, 58]],
];

// Opacity of a bar track, which is the bar color laid over the surface.
export const TRACK_OPACITY = 0.22;

// The two inks laid over a colored fill, such as the reading on a tray icon:
// white, and a near black for a fill too pale to carry white.
export const SURFACE_BASE = '#1c1c1e';
export const LIGHT_INK = '#ffffff';

// Contrast below which white stops reading against a color.
const MIN_LIGHT_CONTRAST = 2.5;

// Contrast below which an accent no longer reads as a mark on a surface, and the
// text color of that surface stands in for it. The OpenAI mark is white, which
// vanishes on a light surface, so this is what turns it dark there.
const MIN_ACCENT_CONTRAST = 2.0;

// The flyout surface and the three text colors of each app mode.
const DARK_PALETTE = {
	dark: true,
	surface: '#2c2c2c',
	labelPrimary: '#ffffff',
	labelSecondary: '#cecece',
	labelTertiary: '#9c9c9c',
};

const LIGHT_PALETTE = {
	dark: false,
	surface: '#f9f9f9',
	labelPrimary: '#1a1a1a',
	labelSecondary: '#5f5f5f',
	labelTertiary: '#8a8a8a',
};

// Size in points and weight of each text style.
const TEXT_STYLES = {
	title: [12, 'bold'],
	section: [10, 'bold'],
	row: [10, 'normal'],
	row_value: [10, 'normal'],
	caption: [8, 'normal'],
	caption_strong: [8, 'bold'],
};

const INTERFACE_SCHEMA = 'org.gnome.desktop.interface';

// Return the settings the palette and the type face are read from.
export function interfaceSettings() {
	return new Gio.Settings({schema_id: INTERFACE_SCHEMA});
}

// Return the palette of the app mode the user chose, asked the way the Linux
// backend asks: the color scheme first, then whether the GTK theme is dark.
// Nothing saying dark means light, which is what every desktop starts in.
export function currentPalette(settings) {
	if (settings.get_string('color-scheme') === 'prefer-dark') {
		return DARK_PALETTE;
	}
	if (settings.get_string('gtk-theme').toLowerCase().includes('dark')) {
		return DARK_PALETTE;
	}
	return LIGHT_PALETTE;
}

// Return the CSS of a text style in a color.
export function textStyle(name, color) {
	const [size, weight] = TEXT_STYLES[name];
	return `font-size: ${size}pt; font-weight: ${weight}; color: ${color};`;
}

// Return a "#rrggbb" color as [red, green, blue].
export function hexToRgb(color) {
	const value = color.replace('#', '');
	return [0, 2, 4].map(index => parseInt(value.slice(index, index + 2), 16));
}

// Return [red, green, blue] as a "#rrggbb" color.
function rgbToHex(rgb) {
	return `#${rgb.map(value => Math.round(value).toString(16).padStart(2, '0')).join('')}`;
}

// Return the ramp color of a usage percentage, as [red, green, blue].
export function usageRgb(percent) {
	const value = Math.min(Math.max(percent, 0), 100);
	let [previousStop, previousColor] = USAGE_RAMP[0];
	for (const [stop, color] of USAGE_RAMP) {
		if (value <= stop) {
			const span = stop - previousStop;
			const ratio = span <= 0 ? 0 : (value - previousStop) / span;
			return previousColor.map((low, index) => Math.round(low + (color[index] - low) * ratio));
		}
		[previousStop, previousColor] = [stop, color];
	}
	return USAGE_RAMP[USAGE_RAMP.length - 1][1];
}

// Return the ramp color of a usage percentage, as "#rrggbb".
export function usageHex(percent) {
	return rgbToHex(usageRgb(percent));
}

// Return the color that results from laying one color over another.
export function mixHex(background, foreground, amount) {
	const lower = hexToRgb(background);
	const upper = hexToRgb(foreground);
	return rgbToHex(lower.map((low, index) => low + (upper[index] - low) * amount));
}

// Return the track color of a bar, which is the bar color dimmed.
export function trackHex(percent, surface) {
	return mixHex(surface, usageHex(percent), TRACK_OPACITY);
}

// Return the relative luminance of [red, green, blue], as sRGB defines it.
function relativeLuminance(rgb) {
	const channels = rgb.map(value => {
		const share = value / 255;
		return share <= 0.04045 ? share / 12.92 : ((share + 0.055) / 1.055) ** 2.4;
	});
	return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

// Return the WCAG contrast ratio between two "#rrggbb" colors.
function contrastRatio(first, second) {
	const one = relativeLuminance(hexToRgb(first));
	const two = relativeLuminance(hexToRgb(second));
	return (Math.max(one, two) + 0.05) / (Math.min(one, two) + 0.05);
}

// Return whether white reads against a "#rrggbb" color.
export function carriesLightText(color) {
	return 1.05 / (relativeLuminance(hexToRgb(color)) + 0.05) >= MIN_LIGHT_CONTRAST;
}

// Return the color a brand accent is drawn in on a palette's surface.
export function readableAccent(accent, palette) {
	if (contrastRatio(accent, palette.surface) < MIN_ACCENT_CONTRAST) {
		return palette.labelPrimary;
	}
	return accent;
}
