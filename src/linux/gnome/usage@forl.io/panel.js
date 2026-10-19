/*
 * The menu the indicator opens, laid out as a GNOME menu.
 *
 * FORL's own panel draws a surface of its own, with tabs, its own type ramp and
 * its own colors, which reads as foreign in the top bar of GNOME. This menu
 * shows the same readings in the Shell's own menu items instead, so it takes
 * the theme's surface, text, fonts, spacing and highlight like every other menu
 * in the bar. Each service is one section, one after the other rather than
 * behind tabs, as the Shell lists devices: a header with the provider mark, the
 * name and the plan, then one item per usage chosen for the panel, with the
 * name and the percentage over a level bar and when it resets under it, the
 * split by product under its own heading, and the line saying when the next
 * reading comes.
 *
 * What the panel lets the user change, signing in and the settings, stays in
 * FORL: those items open FORL's own panel there, as a Mac widget opens the app.
 * While FORL is not running, the menu says so and offers to start it.
 */

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {formatNextUpdate, formatPercent, formatSubtitle} from './formatting.js';
import {foregroundOf} from './icon.js';
import {troughCss, usageHex} from './theme.js';

// Width of a level bar, which sets the width of the menu, and its thickness, in
// pixels before the Shell scales the interface. GNOME draws level bars this
// thick in its menus.
const BAR_WIDTH = 280;
const BAR_HEIGHT = 6;

const MARK_SIZE = 16;
const SPINNER_SIZE = 12;
const SPINNER_EXTENT = 110;
const SPINNER_STROKE = 1.5;
const SPINNER_DEGREES_PER_SECOND = 320;

// Opacity of secondary text, as GNOME dims the text under a title.
const DIM_OPACITY = 166;

// How long a bar takes to reach a new reading, in milliseconds.
const BAR_DURATION = 650;

const PRODUCT_GROUP = 'product';
const PRODUCT_SECTION_TITLE = "This week's usage by product";
const LOADING_TEXT = 'Loading';
const NOT_SIGNED_IN_TEXT = 'Not signed in';
const NEXT_UPDATE_PREFIX = 'Next update in';
const NO_SERVICES_TEXT = 'Start FORL to see your usage here.';
const SIGN_IN_TEXT = 'Sign in to {label}…';
const NOT_RUNNING_TEXT = 'FORL is not running';
const START_TEXT = 'Start FORL';
const SETTINGS_TEXT = 'FORL Settings';

// The views of FORL's panel the menu can open.
const USAGE_VIEW = 'usage';
const SETTINGS_VIEW = 'settings';

// What makes a box lay its children out in a column. GNOME 48 replaced the
// vertical property with orientation, and later releases dropped vertical.
const COLUMN = 'orientation' in St.BoxLayout.prototype
	? {orientation: Clutter.Orientation.VERTICAL}
	: {vertical: true};

// Return a label, dimmed when it is secondary, and smaller when it is a
// caption, as GNOME sets the line under a title.
function label(text, {dim = false, caption = false, bold = false, expand = false} = {}) {
	const style = [caption ? 'font-size: 0.9em;' : '', bold ? 'font-weight: bold;' : ''].join(' ');
	const widget = new St.Label({text, style, x_expand: expand, y_align: Clutter.ActorAlign.CENTER});
	if (dim) {
		widget.opacity = DIM_OPACITY;
	}
	return widget;
}

// Return a menu item that only shows something.
function infoItem() {
	return new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
}

export class Panel {
	// onOpen is called with a service key, or an empty string, and a view, to
	// open FORL's own panel.
	constructor(menu, marks, onOpen) {
		this._menu = menu;
		this._marks = marks;
		this._onOpen = onOpen;
		// The share each bar last showed, so a new reading moves a bar from where
		// it is rather than from empty.
		this._fractions = new Map();
		this._countdowns = [];
		this._spinners = [];
		this._started = GLib.get_monotonic_time();
	}

	// Fill the menu again for a document FORL sent, with the user's accent
	// color, at a scale. fromEmpty is true when the menu has just opened, which
	// is when the bars fill from empty.
	build(document, accent, scale, fromEmpty) {
		this._accent = accent;
		this._scale = scale;
		this._countdowns = [];
		this._spinners = [];
		this._foreground = foregroundOf(this._menu.box);
		this._menu.removeAll();

		if (document.running === false) {
			this._addCaption(NOT_RUNNING_TEXT);
			this._menu.addAction(START_TEXT, () => this._onOpen('', USAGE_VIEW));
			return;
		}
		const services = Array.isArray(document.services) ? document.services : [];
		if (services.length === 0) {
			this._addCaption(NO_SERVICES_TEXT);
			return;
		}
		services.forEach((service, index) => {
			if (index > 0) {
				this._menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
			}
			this._addService(service, document.show_plan !== false, fromEmpty);
		});
		this._menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
		this._menu.addAction(SETTINGS_TEXT, () => this._onOpen('', SETTINGS_VIEW));
		this.tick();
	}

	// Step what changes between readings: the countdowns and the spinners.
	// Called on a short timer while the menu is open.
	tick() {
		for (const countdown of this._countdowns) {
			const due = GLib.DateTime.new_from_iso8601(countdown.due, null);
			if (due === null) {
				continue;
			}
			const text = formatNextUpdate(due.difference(GLib.DateTime.new_now_utc()) / 1e6);
			if (countdown.label.text !== text) {
				countdown.label.text = text;
			}
		}
		for (const spinner of this._spinners) {
			spinner.queue_repaint();
		}
	}

	// One service: its header, and its readings or the way to sign in.
	_addService(service, showPlan, fromEmpty) {
		this._addHeader(service, showPlan);
		if (!service.signed_in) {
			this._menu.addAction(SIGN_IN_TEXT.replace('{label}', service.label), () => this._onOpen(service.key, USAGE_VIEW));
			if (service.status && service.status !== NOT_SIGNED_IN_TEXT) {
				this._addCaption(service.status);
			}
			return;
		}
		const loading = (service.usages || []).length === 0 && service.status === LOADING_TEXT;
		if (!loading) {
			this._addUsages(service, fromEmpty);
		}
		this._addFooter(service, loading);
	}

	// The provider mark, the name, and the plan at the end of the line. A click
	// opens FORL's panel on the service.
	_addHeader(service, showPlan) {
		const item = new PopupMenu.PopupBaseMenuItem();
		const mark = this._marks.icon(service.logo, MARK_SIZE, this._foreground, 'popup-menu-icon');
		mark.y_align = Clutter.ActorAlign.CENTER;
		item.add_child(mark);
		item.add_child(label(service.label, {bold: true, expand: true}));
		if (showPlan && service.plan) {
			item.add_child(label(service.plan, {dim: true, caption: true}));
		}
		item.connect('activate', () => this._onOpen(service.key, USAGE_VIEW));
		this._menu.addMenuItem(item);
	}

	// The usages the user chose to see, the products under their own heading,
	// and any extra usage after them.
	_addUsages(service, fromEmpty) {
		const usages = (service.usages || []).filter(usage => usage.in_panel);
		for (const usage of usages.filter(usage => usage.group !== PRODUCT_GROUP)) {
			this._addRow(service.key, `limit:${usage.key}`, usage.label, formatSubtitle(usage), usage.percent, fromEmpty);
		}
		const products = usages.filter(usage => usage.group === PRODUCT_GROUP);
		if (products.length > 0) {
			this._addHeading(PRODUCT_SECTION_TITLE);
			for (const usage of products) {
				this._addRow(service.key, usage.key, usage.label, '', usage.percent, fromEmpty);
			}
		}
		if (service.extra && service.extra.label) {
			this._addHeading(service.extra.label);
			this._addRow(service.key, 'extra', service.extra.label, '', service.extra.percent, fromEmpty);
		}
	}

	// A heading inside a service, set as GNOME sets the title of a group.
	_addHeading(title) {
		const item = infoItem();
		item.add_child(label(title, {dim: true, caption: true, bold: true}));
		this._menu.addMenuItem(item);
	}

	// A line of secondary text that may run long.
	_addCaption(text) {
		const item = infoItem();
		const caption = label(text, {dim: true, caption: true, expand: true});
		caption.clutter_text.line_wrap = true;
		item.add_child(caption);
		this._menu.addMenuItem(item);
	}

	// One usage: the name and the percentage on one line, the level bar under
	// them, and the line saying when it resets under the bar.
	_addRow(serviceKey, key, name, subtitle, value, fromEmpty) {
		const percent = Math.min(Math.max(Number(value) || 0, 0), 100);
		const item = infoItem();
		const column = new St.BoxLayout({...COLUMN, x_expand: true, style: 'spacing: 4px;'});

		const line = new St.BoxLayout();
		line.add_child(label(name, {expand: true}));
		line.add_child(label(formatPercent(percent), {dim: true, bold: true}));
		column.add_child(line);

		const radius = BAR_HEIGHT / 2;
		const trough = new St.Widget({
			style: `width: ${BAR_WIDTH}px; height: ${BAR_HEIGHT}px; border-radius: ${radius}px; background-color: ${troughCss(this._foreground)};`,
		});
		const fill = new St.Widget({
			style: `height: ${BAR_HEIGHT}px; border-radius: ${radius}px; background-color: ${usageHex(percent, this._accent)};`,
		});
		trough.add_child(fill);
		column.add_child(trough);
		this._animateBar(`${serviceKey}:${key}`, fill, percent / 100, fromEmpty);

		for (const text of subtitle ? subtitle.split('\n') : []) {
			column.add_child(label(text, {dim: true, caption: true}));
		}
		item.add_child(column);
		this._menu.addMenuItem(item);
	}

	// Move a bar's fill from the share it last showed to a new one. A fill
	// shorter than the bar is round is drawn as the round end alone, so a small
	// reading still shows something, and an empty bar shows no fill at all.
	_animateBar(key, fill, fraction, fromEmpty) {
		const widthFor = share => (share <= 0 ? 0 : Math.max(BAR_HEIGHT, BAR_WIDTH * share) * this._scale);
		const from = fromEmpty ? 0 : (this._fractions.get(key) ?? 0);
		this._fractions.set(key, fraction);
		fill.set_width(widthFor(from));
		fill.ease({width: widthFor(fraction), duration: BAR_DURATION, mode: Clutter.AnimationMode.EASE_OUT_CUBIC});
	}

	// The line saying when the next reading comes, or what went wrong, with a
	// spinner at the end while a reading is in flight.
	_addFooter(service, loading) {
		const text = loading ? `${LOADING_TEXT}…` : service.status || '';
		if (!text && !service.refreshing) {
			return;
		}
		const item = infoItem();
		const status = label(text, {dim: true, caption: true, expand: true});
		status.clutter_text.line_wrap = true;
		item.add_child(status);
		if (!loading && service.next_update_at && text.startsWith(NEXT_UPDATE_PREFIX)) {
			this._countdowns.push({label: status, due: service.next_update_at});
		}
		if (loading || service.refreshing) {
			item.add_child(this._spinner());
		}
		this._menu.addMenuItem(item);
	}

	// Return a spinner: an arc in the menu's text color, turning.
	_spinner() {
		const area = new St.DrawingArea({
			style: `width: ${SPINNER_SIZE}px; height: ${SPINNER_SIZE}px;`,
			y_align: Clutter.ActorAlign.CENTER,
			opacity: DIM_OPACITY,
		});
		area.connect('repaint', () => {
			const cr = area.get_context();
			const [width, height] = area.get_surface_size();
			const color = area.get_theme_node().get_foreground_color();
			const stroke = Math.max(1, SPINNER_STROKE * this._scale);
			const radius = (Math.min(width, height) - stroke) / 2;
			const seconds = (GLib.get_monotonic_time() - this._started) / 1e6;
			const start = -((seconds * SPINNER_DEGREES_PER_SECOND) % 360) * Math.PI / 180;
			cr.setLineWidth(stroke);
			cr.setSourceRGBA(color.red / 255, color.green / 255, color.blue / 255, 1);
			cr.arc(width / 2, height / 2, radius, start - SPINNER_EXTENT * Math.PI / 180, start);
			cr.stroke();
			cr.$dispose();
		});
		this._spinners.push(area);
		return area;
	}
}
