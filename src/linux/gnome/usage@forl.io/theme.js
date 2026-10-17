/*
 * The colors the extension adds to the Shell's own.
 *
 * Everything else, the surface of the menu, its text, its fonts and its
 * highlight, comes from the Shell theme, so the menu looks like every other
 * menu in the top bar, in light and in dark style alike. What the theme has no
 * word for is the fill of a usage bar: that is drawn in the accent color the
 * user picked in Settings, as GNOME draws a level bar, and turns to the
 * warning and then the error color of the Adwaita palette at the thresholds
 * src/common/ui/status.py gives the Waybar classes. Change those there and
 * change them here.
 */

import Gio from 'gi://Gio';

export const WARNING_PERCENT = 50;
export const CRITICAL_PERCENT = 80;

// The Adwaita accent colors, by the name org.gnome.desktop.interface stores.
// GNOME before 47 has no choice of accent and draws everything in blue.
const ACCENT_COLORS = {
	blue: '#3584e4',
	teal: '#2190a4',
	green: '#3a944a',
	yellow: '#c88800',
	orange: '#ed5b00',
	red: '#e62d42',
	pink: '#d56199',
	purple: '#9141ac',
	slate: '#6f8396',
};
const DEFAULT_ACCENT = 'blue';

const WARNING_COLOR = '#e5a50a';
const ERROR_COLOR = '#e01b24';

// Opacity of the empty part of a bar, which is the menu's text color faded, as
// the trough of a GNOME level bar is.
const TROUGH_OPACITY = 0.15;

const INTERFACE_SCHEMA = 'org.gnome.desktop.interface';
const ACCENT_KEY = 'accent-color';

// Return the settings the accent color is read from.
export function interfaceSettings() {
	return new Gio.Settings({schema_id: INTERFACE_SCHEMA});
}

// Return the accent color the user chose, as "#rrggbb".
export function accentHex(settings) {
	if (!settings.settings_schema.has_key(ACCENT_KEY)) {
		return ACCENT_COLORS[DEFAULT_ACCENT];
	}
	return ACCENT_COLORS[settings.get_string(ACCENT_KEY)] ?? ACCENT_COLORS[DEFAULT_ACCENT];
}

// Return the fill color of a bar at a usage percentage.
export function usageHex(percent, accent) {
	if (percent >= CRITICAL_PERCENT) {
		return ERROR_COLOR;
	}
	if (percent >= WARNING_PERCENT) {
		return WARNING_COLOR;
	}
	return accent;
}

// Return the color the top bar shows a reading in: the bar's own text color,
// unless the window is nearly spent, which is worth a glance.
export function readingColor(percent) {
	return percent >= CRITICAL_PERCENT ? ERROR_COLOR : null;
}

// Return a Clutter color as "#rrggbb".
export function colorHex(color) {
	return `#${[color.red, color.green, color.blue].map(value => value.toString(16).padStart(2, '0')).join('')}`;
}

// Return the trough color of a bar under a text color, as CSS.
export function troughCss(foreground) {
	return `rgba(${foreground.red}, ${foreground.green}, ${foreground.blue}, ${TROUGH_OPACITY})`;
}
