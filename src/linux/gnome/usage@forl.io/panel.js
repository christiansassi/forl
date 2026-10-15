/*
 * The page the menu shows, laid out as src/common/ui/panel.py lays out the
 * panel of the Windows and Linux widgets.
 *
 * A row of tabs picks the service. Under it, a service someone is signed in to
 * shows its mark, its name and its plan, then one row per usage chosen for the
 * panel, with the name and what it covers on the left, a thin bar across the
 * middle and the percentage on the right, any split by product under its own
 * title, and a line counting down to the next reading. A service nobody is
 * signed in to says so where the panel offers the sign-in. Until the first
 * reading arrives, the page is a pulsing skeleton of the rows to come.
 *
 * Every distance is the panel's, in the same layout units, and the Shell scales
 * them with the display as Windows and Tk do. The colors come from theme.js.
 * What the panel lets the user change, the settings behind its gear and the
 * sign-in itself, stays in FORL: the gear and the sign-in open FORL's own panel
 * there, as a Mac widget opens the app. While FORL is not running, the page
 * says so and offers to start it.
 */

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {formatNextUpdate, formatPercent, formatSubtitle} from './formatting.js';
import {mixHex, readableAccent, textStyle, trackHex, usageHex} from './theme.js';

const PANEL_WIDTH = 430;
const PANEL_PAD = 20;
const CONTENT_WIDTH = PANEL_WIDTH - 2 * PANEL_PAD;

const LABEL_COLUMN_WIDTH = 176;
const BAR_COLUMN_LEFT = 206;
const VALUE_COLUMN_WIDTH = 46;
const BAR_HEIGHT = 5;
const BAR_WIDTH = PANEL_WIDTH - PANEL_PAD - VALUE_COLUMN_WIDTH - BAR_COLUMN_LEFT;

const LOGO_SIZE = 17;
const LOGO_TITLE_GAP = 9;
const PLAN_GAP = 10;
const HEADER_GAP = 14;

const TAB_HEIGHT = 30;
const TAB_GAP = 4;
const TAB_RADIUS = 7;
const TAB_MARK_SIZE = 14;
const TAB_MARK_GAP = 6;
const TAB_FILL_OPACITY = 0.14;
const TAB_STROKE_OPACITY = 0.35;
const TABS_GAP = 14;

const SIGN_IN_PAGE_PAD = 12;
const SIGN_IN_BUTTON_HEIGHT = 44;

const LIMIT_ROW_MIN_HEIGHT = 34;
const LIMIT_ROW_GAP = 14;
const PRODUCT_ROW_MIN_HEIGHT = 22;
const PRODUCT_ROW_GAP = 10;
const SECTION_TITLE_GAP = 26;
const SECTION_TITLE_LEAD = 6;
const FOOTER_LEAD = 4;
const FOOTER_HEIGHT = 20;

const SPINNER_SIZE = 13;
const SPINNER_EXTENT = 110;
const SPINNER_STROKE = 2;
const SPINNER_DEGREES_PER_SECOND = 320;

// How long a bar takes to reach a new reading, in milliseconds. The panel moves
// its bars on a critically damped spring of response 0.45, which comes to rest
// in about this long.
const BAR_DURATION = 650;

const SKELETON_ROWS = [110, 80];
const SKELETON_SUBTITLE_OFFSET = 17;
const SKELETON_SUBTITLE_WIDTH = 150;
const SKELETON_TEXT_HEIGHT = 10;
const SKELETON_CAPTION_HEIGHT = 8;
const SKELETON_TEXT_INSET = 3;
const SKELETON_VALUE_WIDTH = 30;
const SKELETON_PLAN_WIDTH = 36;
const SKELETON_FOOTER_WIDTH = 130;
const SKELETON_RADIUS = 3;
const SKELETON_LOW_OPACITY = 0.07;
const SKELETON_HIGH_OPACITY = 0.16;
const SKELETON_PERIOD_SECONDS = 1.4;

const PRODUCT_GROUP = 'product';
const PRODUCT_SECTION_TITLE = "This week's usage by product";
const LOADING_TEXT = 'Loading';
const NOT_SIGNED_IN_TEXT = 'Not signed in';
const NEXT_UPDATE_PREFIX = 'Next update in';
const NO_SERVICES_TEXT = 'Start FORL to see your usage here.';
const SIGN_IN_TEXT = 'Sign in to {label}';
const NOT_RUNNING_TEXT = 'FORL is not running.';
const START_TEXT = 'Start FORL';

// The views of FORL's panel the page can open.
const USAGE_VIEW = 'usage';
const SETTINGS_VIEW = 'settings';

// The gear, drawn from the icon theme in the panel's size.
const GEAR_ICON = 'emblem-system-symbolic';
const CONTROL_SIZE = 16;

// What makes a box lay its children out in a column. GNOME 48 replaced the
// vertical property with orientation, and later releases dropped vertical.
const COLUMN = 'orientation' in St.BoxLayout.prototype
	? {orientation: Clutter.Orientation.VERTICAL}
	: {vertical: true};

// Return an empty block of a height, which is how the page keeps the panel's
// vertical rhythm between the things on it.
function spacer(height) {
	return new St.Widget({style: `height: ${height}px;`});
}

// Return a label in a text style and a color.
function label(text, style, color, extra = '') {
	return new St.Label({text, style: `${textStyle(style, color)} ${extra}`});
}

// Return words that act when clicked and are underlined while the pointer is
// over them, as the panel's actions are.
function action(text, style, color, onClick) {
	const words = label(text, style, color);
	const button = new St.Button({child: words, can_focus: true});
	button.connect('notify::hover', () => {
		words.set_style(`${textStyle(style, color)} text-decoration: ${button.hover ? 'underline' : 'none'};`);
	});
	button.connect('clicked', onClick);
	return button;
}

export class Panel {
	// onOpen is called with a service key, or an empty string, and a view, to
	// open FORL's own panel.
	constructor(assetsPath, onOpen) {
		this._onOpen = onOpen;
		this.actor = new St.BoxLayout({...COLUMN, style: `width: ${CONTENT_WIDTH}px;`});
		this._assetsPath = assetsPath;
		this._selected = '';
		this._svgs = new Map();
		// The share each bar last showed, so a new reading moves a bar from where
		// it is rather than from empty, as the panel's springs do.
		this._fractions = new Map();
		this._skeletons = [];
		this._countdown = null;
		this._spinner = null;
		this._started = GLib.get_monotonic_time();
	}

	// Choose the service whose tab the page opens on.
	select(key) {
		this._selected = key;
	}

	// Lay the page out again for a document FORL wrote, in a palette, at a
	// scale. fromEmpty is true when the menu has just opened, which is when the
	// panel fills its bars from empty.
	build(document, palette, scale, fromEmpty) {
		this._document = document;
		this._palette = palette;
		this._scale = scale;
		this._skeletons = [];
		this._countdown = null;
		this._spinner = null;
		this.actor.destroy_all_children();

		if (document.running === false) {
			this._addNotRunningPage();
			return;
		}
		const services = Array.isArray(document.services) ? document.services : [];
		if (services.length === 0) {
			this.actor.add_child(label(NO_SERVICES_TEXT, 'caption', palette.labelSecondary));
			return;
		}
		if (!services.some(service => service.key === this._selected)) {
			this._selected = services[0].key;
		}
		const current = services.find(service => service.key === this._selected);
		this._accent = readableAccent(current.accent, palette);

		this._addTabs(services);
		if (!current.signed_in) {
			this._addSignInPage(current);
			return;
		}
		const loading = (current.usages || []).length === 0 && current.status === LOADING_TEXT;
		this._addHeader(current, document.show_plan !== false, loading);
		if (loading) {
			this._addSkeletonRows();
		} else {
			this._addBody(current, fromEmpty);
		}
		this._addFooter(current, loading);
		this.tick();
	}

	// Step what changes between readings: the countdown, the spinner and the
	// pulse of the skeleton. Called on a short timer while the menu is open.
	tick() {
		const seconds = (GLib.get_monotonic_time() - this._started) / 1e6;
		if (this._skeletons.length > 0) {
			const phase = (seconds % SKELETON_PERIOD_SECONDS) / SKELETON_PERIOD_SECONDS;
			const swing = 0.5 - 0.5 * Math.cos(2 * Math.PI * phase);
			const opacity = SKELETON_LOW_OPACITY + (SKELETON_HIGH_OPACITY - SKELETON_LOW_OPACITY) * swing;
			const shade = mixHex(this._palette.surface, this._palette.labelPrimary, opacity);
			for (const block of this._skeletons) {
				block.set_style(`${block._forlShape} background-color: ${shade};`);
			}
		}
		if (this._countdown !== null) {
			const due = GLib.DateTime.new_from_iso8601(this._countdown.due, null);
			if (due !== null) {
				const left = due.difference(GLib.DateTime.new_now_utc()) / 1e6;
				const text = formatNextUpdate(left);
				if (this._countdown.label.text !== text) {
					this._countdown.label.text = text;
				}
			}
		}
		this._spinner?.queue_repaint();
	}

	// Return the image of a provider mark in a color, or null when the artwork
	// is missing. The mark is read once, and the color written into it, so it is
	// drawn by the Shell at whatever size it is shown.
	_mark(service, size, color) {
		let svg = this._svgs.get(service.logo);
		if (svg === undefined) {
			try {
				const [, contents] = GLib.file_get_contents(GLib.build_filenamev([this._assetsPath, service.logo || '']));
				svg = new TextDecoder().decode(contents);
			} catch (error) {
				svg = null;
			}
			this._svgs.set(service.logo, svg);
		}
		if (svg === null) {
			return new St.Widget({style: `width: ${size}px; height: ${size}px;`});
		}
		const colored = svg.replace(/fill="[^"]*"/g, `fill="${color}"`);
		const gicon = Gio.BytesIcon.new(new GLib.Bytes(new TextEncoder().encode(colored)));
		return new St.Icon({gicon, icon_size: size});
	}

	// The tabs across the top. The selected one is tinted with its service's
	// accent, filled lightly and outlined a little more strongly, and the one
	// under the pointer takes its service's color.
	_addTabs(services) {
		const palette = this._palette;
		const row = new St.BoxLayout({style: `spacing: ${TAB_GAP}px;`});
		const width = (CONTENT_WIDTH - TAB_GAP * (services.length - 1)) / services.length;
		for (const service of services) {
			const selected = service.key === this._selected;
			const accent = readableAccent(service.accent, palette);
			const plate = selected
				? `background-color: ${mixHex(palette.surface, accent, TAB_FILL_OPACITY)}; border: 1px solid ${mixHex(palette.surface, accent, TAB_STROKE_OPACITY)};`
				: 'border: 1px solid transparent;';
			const content = new St.BoxLayout({style: `spacing: ${TAB_MARK_GAP}px;`, x_align: Clutter.ActorAlign.CENTER, x_expand: true});
			content.add_child(this._mark(service, TAB_MARK_SIZE, accent));
			const style = selected ? 'section' : 'row';
			const name = label(service.label, style, selected ? accent : palette.labelSecondary);
			name.y_align = Clutter.ActorAlign.CENTER;
			content.add_child(name);
			const tab = new St.Button({
				child: content,
				reactive: !selected,
				style: `width: ${width}px; height: ${TAB_HEIGHT}px; border-radius: ${TAB_RADIUS}px; ${plate}`,
			});
			if (!selected) {
				tab.connect('notify::hover', () => {
					name.set_style(textStyle(style, tab.hover ? accent : palette.labelSecondary));
				});
				tab.connect('clicked', () => {
					this._selected = service.key;
					this.build(this._document, this._palette, this._scale, true);
				});
			}
			row.add_child(tab);
		}
		this.actor.add_child(row);
		this.actor.add_child(spacer(TABS_GAP));
	}

	// What the page says while FORL is not running, and the way to start it.
	_addNotRunningPage() {
		const palette = this._palette;
		this.actor.add_child(spacer(SIGN_IN_PAGE_PAD));
		const message = label(NOT_RUNNING_TEXT, 'caption', palette.labelSecondary);
		message.x_align = Clutter.ActorAlign.CENTER;
		this.actor.add_child(message);
		const box = new St.BoxLayout({style: `height: ${SIGN_IN_BUTTON_HEIGHT}px;`});
		const start = action(START_TEXT, 'title', palette.labelPrimary, () => this._onOpen('', USAGE_VIEW));
		start.x_expand = true;
		start.x_align = Clutter.ActorAlign.CENTER;
		start.y_align = Clutter.ActorAlign.CENTER;
		box.add_child(start);
		this.actor.add_child(box);
		this.actor.add_child(spacer(SIGN_IN_PAGE_PAD));
	}

	// What a service nobody is signed in to shows, where the panel offers the
	// sign-in, and why the last attempt failed when it did.
	_addSignInPage(service) {
		const palette = this._palette;
		this.actor.add_child(spacer(SIGN_IN_PAGE_PAD));
		const box = new St.BoxLayout({style: `height: ${SIGN_IN_BUTTON_HEIGHT}px;`});
		const prompt = action(SIGN_IN_TEXT.replace('{label}', service.label), 'title', this._accent, () => this._onOpen(service.key, USAGE_VIEW));
		prompt.x_expand = true;
		prompt.x_align = Clutter.ActorAlign.CENTER;
		prompt.y_align = Clutter.ActorAlign.CENTER;
		box.add_child(prompt);
		this.actor.add_child(box);
		if (service.status && service.status !== NOT_SIGNED_IN_TEXT) {
			const message = label(service.status, 'caption', palette.labelSecondary);
			message.clutter_text.line_wrap = true;
			this.actor.add_child(message);
		}
		this.actor.add_child(spacer(SIGN_IN_PAGE_PAD));
	}

	// The provider mark, its name, and the plan beside the name.
	_addHeader(service, showPlan, loading) {
		const palette = this._palette;
		const header = new St.BoxLayout({style: `padding-bottom: ${HEADER_GAP}px;`});
		const mark = this._mark(service, LOGO_SIZE, this._accent);
		mark.y_align = Clutter.ActorAlign.CENTER;
		header.add_child(mark);
		header.add_child(label(service.label, 'title', palette.labelPrimary, `padding-left: ${LOGO_TITLE_GAP}px;`));
		if (showPlan && loading) {
			const block = this._skeleton(SKELETON_PLAN_WIDTH, SKELETON_CAPTION_HEIGHT);
			const holder = new St.Bin({child: block, style: `padding-left: ${PLAN_GAP}px;`, y_align: Clutter.ActorAlign.CENTER});
			header.add_child(holder);
		} else if (showPlan && service.plan) {
			// The two runs sit on one baseline, as in the panel: the smaller one
			// is set at the bottom of the line, lifted by what a smaller face
			// reserves under its baseline.
			const plan = label(service.plan, 'caption_strong', palette.labelTertiary, `padding-left: ${PLAN_GAP}px; padding-bottom: 2px;`);
			plan.y_align = Clutter.ActorAlign.END;
			header.add_child(plan);
		}
		header.add_child(new St.Widget({x_expand: true}));
		header.add_child(this._gear(service));
		this.actor.add_child(header);
	}

	// Return the gear that opens FORL's settings, which turns the service's
	// color under the pointer as the panel's controls do.
	_gear(service) {
		const palette = this._palette;
		const icon = new St.Icon({icon_name: GEAR_ICON, icon_size: CONTROL_SIZE, style: `color: ${palette.labelSecondary};`});
		const button = new St.Button({child: icon, can_focus: true, y_align: Clutter.ActorAlign.CENTER});
		button.connect('notify::hover', () => {
			icon.set_style(`color: ${button.hover ? this._accent : palette.labelSecondary};`);
		});
		button.connect('clicked', () => this._onOpen(service.key, SETTINGS_VIEW));
		return button;
	}

	// The usage rows the user chose to see, the products under their own title,
	// and any extra usage after them.
	_addBody(service, fromEmpty) {
		const usages = (service.usages || []).filter(usage => usage.in_panel);
		for (const usage of usages.filter(usage => usage.group !== PRODUCT_GROUP)) {
			this._addRow(`limit:${usage.key}`, usage.label, formatSubtitle(usage), usage.percent, LIMIT_ROW_MIN_HEIGHT, fromEmpty);
			this.actor.add_child(spacer(LIMIT_ROW_GAP));
		}
		const products = usages.filter(usage => usage.group === PRODUCT_GROUP);
		if (products.length > 0) {
			this._addSectionTitle(PRODUCT_SECTION_TITLE);
			for (const usage of products) {
				this._addRow(usage.key, usage.label, '', usage.percent, PRODUCT_ROW_MIN_HEIGHT, fromEmpty);
				this.actor.add_child(spacer(PRODUCT_ROW_GAP));
			}
		}
		if (service.extra && service.extra.label) {
			this._addSectionTitle(service.extra.label);
			this._addRow('extra', service.extra.label, '', service.extra.percent, PRODUCT_ROW_MIN_HEIGHT, fromEmpty);
			this.actor.add_child(spacer(PRODUCT_ROW_GAP));
		}
	}

	// A section heading.
	_addSectionTitle(title) {
		this.actor.add_child(spacer(SECTION_TITLE_LEAD));
		const box = new St.BoxLayout({style: `height: ${SECTION_TITLE_GAP}px;`});
		box.add_child(label(title, 'section', this._palette.labelPrimary));
		this.actor.add_child(box);
	}

	// One usage row: the name and the line under it on the left, the bar and the
	// percentage centered against that block.
	_addRow(key, name, subtitle, value, minHeight, fromEmpty) {
		const palette = this._palette;
		const percent = Math.min(Math.max(Number(value) || 0, 0), 100);
		const row = new St.BoxLayout({style: `min-height: ${minHeight}px;`});

		const names = new St.BoxLayout({
			...COLUMN,
			y_align: Clutter.ActorAlign.START,
			style: `width: ${LABEL_COLUMN_WIDTH}px; padding-right: ${BAR_COLUMN_LEFT - PANEL_PAD - LABEL_COLUMN_WIDTH}px;`,
		});
		const title = label(name, 'row', palette.labelPrimary);
		title.clutter_text.line_wrap = true;
		names.add_child(title);
		if (subtitle) {
			const line = label(subtitle, 'caption', palette.labelSecondary);
			line.clutter_text.line_wrap = true;
			names.add_child(line);
		}
		row.add_child(names);

		const radius = BAR_HEIGHT / 2;
		const track = new St.Widget({
			y_align: Clutter.ActorAlign.CENTER,
			style: `width: ${BAR_WIDTH}px; height: ${BAR_HEIGHT}px; border-radius: ${radius}px; background-color: ${trackHex(percent, palette.surface)};`,
		});
		const fill = new St.Widget({
			style: `height: ${BAR_HEIGHT}px; border-radius: ${radius}px; background-color: ${usageHex(percent)};`,
		});
		track.add_child(fill);
		row.add_child(track);
		this._animateBar(key, fill, percent / 100, fromEmpty);

		const reading = label(formatPercent(percent), 'row_value', palette.labelSecondary, `width: ${VALUE_COLUMN_WIDTH}px; text-align: right;`);
		reading.y_align = Clutter.ActorAlign.CENTER;
		row.add_child(reading);
		this.actor.add_child(row);
	}

	// Move a bar's fill from the share it last showed to a new one. A fill
	// shorter than the bar is round is drawn as the round end alone, so a small
	// reading still shows something, and an empty bar shows no fill at all.
	_animateBar(key, fill, fraction, fromEmpty) {
		const scoped = `${this._selected}:${key}`;
		const widthFor = share => (share <= 0 ? 0 : Math.max(BAR_HEIGHT, BAR_WIDTH * share) * this._scale);
		const from = fromEmpty ? 0 : (this._fractions.get(scoped) ?? 0);
		this._fractions.set(scoped, fraction);
		fill.set_width(widthFor(from));
		fill.ease({width: widthFor(fraction), duration: BAR_DURATION, mode: Clutter.AnimationMode.EASE_OUT_CUBIC});
	}

	// Return one skeleton block, which tick() pulses.
	_skeleton(width, height) {
		const block = new St.Widget();
		block._forlShape = `width: ${width}px; height: ${height}px; border-radius: ${SKELETON_RADIUS}px;`;
		block.set_style(block._forlShape);
		this._skeletons.push(block);
		return block;
	}

	// Rows shaped like the session and weekly rows, in skeleton blocks, with the
	// name, the line under it, the bar and the percentage in the columns a real
	// row puts them in, so the reading lands where the eye already is.
	_addSkeletonRows() {
		const scale = this._scale;
		const right = CONTENT_WIDTH;
		const center = LIMIT_ROW_MIN_HEIGHT / 2;
		for (const labelWidth of SKELETON_ROWS) {
			const row = new St.Widget({style: `width: ${CONTENT_WIDTH}px; height: ${LIMIT_ROW_MIN_HEIGHT}px;`});
			const place = (width, height, x, y) => {
				const block = this._skeleton(width, height);
				block.set_position(Math.round(x * scale), Math.round(y * scale));
				row.add_child(block);
			};
			place(labelWidth, SKELETON_TEXT_HEIGHT, 0, SKELETON_TEXT_INSET);
			place(SKELETON_SUBTITLE_WIDTH, SKELETON_CAPTION_HEIGHT, 0, SKELETON_SUBTITLE_OFFSET + SKELETON_TEXT_INSET);
			place(BAR_WIDTH, BAR_HEIGHT, BAR_COLUMN_LEFT - PANEL_PAD, center - BAR_HEIGHT / 2);
			place(SKELETON_VALUE_WIDTH, SKELETON_TEXT_HEIGHT, right - SKELETON_VALUE_WIDTH, center - SKELETON_TEXT_HEIGHT / 2);
			this.actor.add_child(row);
			this.actor.add_child(spacer(LIMIT_ROW_GAP));
		}
	}

	// The line counting down to the next reading, with a spinner on the right
	// while a reading is in flight. A failure the user can fix, such as a sign-in
	// that ran out, takes the line instead.
	_addFooter(service, loading) {
		const palette = this._palette;
		this.actor.add_child(spacer(FOOTER_LEAD));
		const footer = new St.BoxLayout({style: `height: ${FOOTER_HEIGHT}px;`});
		if (loading) {
			const block = this._skeleton(SKELETON_FOOTER_WIDTH, SKELETON_CAPTION_HEIGHT);
			footer.add_child(new St.Bin({child: block, style: `padding-top: ${SKELETON_TEXT_INSET}px;`, y_align: Clutter.ActorAlign.START}));
			this.actor.add_child(footer);
			return;
		}
		const status = label(service.status || '', 'caption', palette.labelSecondary);
		status.x_expand = true;
		status.y_align = Clutter.ActorAlign.START;
		footer.add_child(status);
		if (service.next_update_at && (service.status || '').startsWith(NEXT_UPDATE_PREFIX)) {
			this._countdown = {label: status, due: service.next_update_at};
		}
		if (service.refreshing) {
			this._spinner = this._spinnerArea();
			footer.add_child(this._spinner);
		}
		this.actor.add_child(footer);
	}

	// Return the spinner: an arc in the service's color, turning.
	_spinnerArea() {
		const area = new St.DrawingArea({style: `width: ${SPINNER_SIZE}px; height: ${SPINNER_SIZE}px;`, y_align: Clutter.ActorAlign.START});
		const [red, green, blue] = [1, 3, 5].map(index => parseInt(this._accent.slice(index, index + 2), 16) / 255);
		area.connect('repaint', () => {
			const cr = area.get_context();
			const [width, height] = area.get_surface_size();
			const stroke = Math.max(1, SPINNER_STROKE * this._scale);
			const radius = (Math.min(width, height) - stroke) / 2;
			const seconds = (GLib.get_monotonic_time() - this._started) / 1e6;
			const start = -((seconds * SPINNER_DEGREES_PER_SECOND) % 360) * Math.PI / 180;
			cr.setLineWidth(stroke);
			cr.setSourceRGBA(red, green, blue, 1);
			cr.arc(width / 2, height / 2, radius, start - SPINNER_EXTENT * Math.PI / 180, start);
			cr.stroke();
			cr.$dispose();
		});
		return area;
	}
}
