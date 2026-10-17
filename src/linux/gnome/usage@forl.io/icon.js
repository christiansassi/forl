/*
 * The marks the extension shows, in the color of the text around them.
 *
 * GNOME draws the icons of the top bar and of its menus as symbolic icons: one
 * color, the text color of where they sit, so they follow the light and dark
 * style and any theme. The provider marks are single color artwork already, so
 * they are written in that color as they are loaded. The app's own icon is a
 * full color smiling face; its outline is drawn here instead, at the pixels it
 * is shown at, as a symbolic icon would draw it.
 */

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {colorHex} from './theme.js';

// Stroke widths of the face, as shares of its edge.
const APP_OUTLINE_RATIO = 0.1;
const APP_EYE_RATIO = 0.12;
const APP_SMILE_RATIO = 0.1;

// Return the foreground color of a widget's theme, or white while the widget
// is not on the stage yet, which is the color of the top bar's text.
export function foregroundOf(widget) {
	if (!widget.get_stage()) {
		return {red: 255, green: 255, blue: 255, alpha: 255};
	}
	return widget.get_theme_node().get_foreground_color();
}

export class Marks {
	constructor(assetsPath) {
		this._assetsPath = assetsPath;
		this._svgs = new Map();
	}

	// Return a provider mark as an icon in a color, or an empty block of its
	// size when the artwork is missing.
	icon(logo, size, color, styleClass = '') {
		let svg = this._svgs.get(logo);
		if (svg === undefined) {
			try {
				const [, contents] = GLib.file_get_contents(GLib.build_filenamev([this._assetsPath, logo || '']));
				svg = new TextDecoder().decode(contents);
			} catch (error) {
				svg = null;
			}
			this._svgs.set(logo, svg);
		}
		if (svg === null) {
			return new St.Widget({style: `width: ${size}px; height: ${size}px;`});
		}
		const hex = colorHex(color);
		// Every fill takes the color, and artwork that leaves its fill to the
		// default black is given one on its root.
		let colored = svg.replace(/fill="[^"]*"/g, `fill="${hex}"`);
		if (!/<svg[^>]*\sfill="/.test(colored)) {
			colored = colored.replace('<svg ', `<svg fill="${hex}" `);
		}
		const gicon = Gio.BytesIcon.new(new GLib.Bytes(new TextEncoder().encode(colored)));
		return new St.Icon({gicon, icon_size: size, style_class: styleClass});
	}
}

// Draw the outline of the app's face on a square area, in the area's own text
// color.
export function drawAppMark(area) {
	const cr = area.get_context();
	const [width, height] = area.get_surface_size();
	const size = Math.min(width, height);
	const color = area.get_theme_node().get_foreground_color();
	cr.setSourceRGBA(color.red / 255, color.green / 255, color.blue / 255, color.alpha / 255);

	const outline = Math.max(1, size * APP_OUTLINE_RATIO);
	const center = size / 2;
	cr.setLineWidth(outline);
	cr.arc(center, center, center - outline / 2, 0, 2 * Math.PI);
	cr.stroke();

	cr.setLineCap(1);
	cr.setLineWidth(Math.max(1, size * APP_EYE_RATIO));
	for (const x of [0.37, 0.63]) {
		cr.moveTo(size * x, size * 0.32);
		cr.lineTo(size * x, size * 0.44);
	}
	cr.stroke();

	cr.setLineWidth(Math.max(1, size * APP_SMILE_RATIO));
	cr.arc(center, size * 0.47, size * 0.24, Math.PI * 0.2, Math.PI * 0.8);
	cr.stroke();
	cr.$dispose();
}
