/*
 * The icons in the top bar, drawn as src/common/render/icon.py draws the tray
 * icons: a rounded column in the color of the service that fills from the
 * bottom as the window is spent, with the reading across the middle of it.
 *
 * The reading is white on a column dark enough to carry white. A column too
 * pale for that, which is what a service colored white has, takes a dark
 * reading and an opaque, dimmed empty part, so the reading has something light
 * to sit on whatever the bar behind it is.
 */

import Pango from 'gi://Pango';
import PangoCairo from 'gi://PangoCairo';

import {LIGHT_INK, SURFACE_BASE, TRACK_OPACITY, carriesLightText, hexToRgb, mixHex} from './theme.js';

// Shape and type of the column, as shares of its edge.
const CORNER_RATIO = 0.26;
const DIGITS_HEIGHT_RATIO = 0.46;
const DIGITS_WIDTH_RATIO = 0.92;

// How far the empty part of a pale column is taken toward the surface color.
const PALE_TRACK_MIX = 0.42;

// What the number reads before the first reading has arrived. A dash has far
// less ink than a digit, so a digit is what its size is measured against.
const NO_READING = '-';
const NO_READING_REFERENCE = '0';

// Trace a rounded rectangle.
function roundedRectangle(cr, size, radius) {
	cr.newSubPath();
	cr.arc(size - radius, radius, radius, -Math.PI / 2, 0);
	cr.arc(size - radius, size - radius, radius, 0, Math.PI / 2);
	cr.arc(radius, size - radius, radius, Math.PI / 2, Math.PI);
	cr.arc(radius, radius, radius, Math.PI, Math.PI * 3 / 2);
	cr.closePath();
}

// Set a "#rrggbb" color, at an opacity, as the source.
function setColor(cr, color, alpha = 1) {
	const [red, green, blue] = hexToRgb(color);
	cr.setSourceRGBA(red / 255, green / 255, blue / 255, alpha);
}

// Return a layout of a text in a bold face sized so the ink of a reference text
// reaches a height, and shrunk if the text would be wider than the column.
function fittedLayout(cr, family, text, reference, targetHeight, maxWidth) {
	const layout = PangoCairo.create_layout(cr);
	const description = Pango.FontDescription.from_string(family);
	description.set_weight(Pango.Weight.BOLD);
	const measure = (pixels, characters) => {
		description.set_absolute_size(Math.max(1, pixels) * Pango.SCALE);
		layout.set_font_description(description);
		layout.set_text(characters, -1);
		return layout.get_pixel_extents()[0];
	};
	const guess = targetHeight * 1.3;
	const ink = measure(guess, reference || text);
	let size = ink.height > 0 ? guess * targetHeight / ink.height : guess;
	const width = measure(size, text).width;
	if (width > maxWidth && width > 0) {
		size = size * maxWidth / width;
	}
	measure(size, text);
	return layout;
}

// Draw one icon on a square area: percent is 0 to 100, or null before the first
// reading, and color is the service's accent as "#rrggbb".
export function drawIcon(cr, size, percent, color, family) {
	const carriesWhite = carriesLightText(color);
	const radius = size * CORNER_RATIO;
	const fraction = percent === null ? 0 : Math.min(Math.max(percent, 0), 100) / 100;
	const level = size - size * fraction;

	roundedRectangle(cr, size, radius);
	if (carriesWhite) {
		setColor(cr, color, TRACK_OPACITY);
	} else {
		setColor(cr, mixHex(color, SURFACE_BASE, PALE_TRACK_MIX));
	}
	cr.fill();

	if (fraction > 0) {
		// The fill is the whole column clipped to below the level, so its bottom
		// keeps the rounded corners of the column and its top stays flat.
		cr.save();
		cr.rectangle(0, level, size, size - level);
		cr.clip();
		roundedRectangle(cr, size, radius);
		setColor(cr, color);
		cr.fill();
		cr.restore();
	}

	const text = percent === null ? NO_READING : `${Math.round(percent)}`;
	const reference = percent === null ? NO_READING_REFERENCE : '';
	const layout = fittedLayout(cr, family, text, reference, size * DIGITS_HEIGHT_RATIO, size * DIGITS_WIDTH_RATIO);
	const ink = layout.get_pixel_extents()[0];
	cr.moveTo(size / 2 - ink.x - ink.width / 2, size / 2 - ink.y - ink.height / 2);
	setColor(cr, carriesWhite ? LIGHT_INK : SURFACE_BASE);
	PangoCairo.show_layout(cr, layout);
}

// The app's own mark, the smiling face of icon.png, redrawn for the top bar.
// Reduced to the size of a bar icon, the artwork keeps its yellow disc and
// loses the face, and its dark outline vanishes against a dark bar, so what is
// left reads as a ring. Drawn here instead, at the pixels it is shown at, with
// strokes thick enough to survive the size, as icons are drawn again for their
// smallest sizes.
const APP_YELLOW = '#ffd626';
const APP_INK = '#000000';
const APP_OUTLINE_RATIO = 0.08;
const APP_EYE_RATIO = 0.12;
const APP_SMILE_RATIO = 0.11;

export function drawAppMark(cr, size) {
	const outline = Math.max(1, size * APP_OUTLINE_RATIO);
	const center = size / 2;
	cr.arc(center, center, center - outline / 2, 0, 2 * Math.PI);
	setColor(cr, APP_YELLOW);
	cr.fillPreserve();
	cr.setLineWidth(outline);
	setColor(cr, APP_INK);
	cr.stroke();

	cr.setLineCap(1);
	cr.setLineWidth(Math.max(1, size * APP_EYE_RATIO));
	for (const x of [0.37, 0.63]) {
		cr.moveTo(size * x, size * 0.30);
		cr.lineTo(size * x, size * 0.44);
	}
	cr.stroke();

	cr.setLineWidth(Math.max(1, size * APP_SMILE_RATIO));
	cr.arc(center, size * 0.45, size * 0.27, Math.PI * 0.18, Math.PI * 0.82);
	cr.stroke();
}
