/*
 * The FORL extension for GNOME Shell 45 and later.
 *
 * FORL writes every reading to ~/.cache/forl/status.json, and this extension
 * reads that file whenever it changes, and every half minute besides, and shows
 * it in the top bar: one line with the usages chosen for the tray, which opens a
 * menu with each service and the usages chosen for the panel, as bars. It reads
 * only what FORL wrote, so FORL must be running for it to change.
 *
 * On a GNOME with the AppIndicator extension, FORL already has icons of its own
 * in the top bar and says so in the file. The indicator then stays hidden
 * rather than show the same readings twice in the same bar.
 */

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

Gio._promisify(Gio.File.prototype, 'load_contents_async');

// How often the file is read again when no change was reported, in seconds,
// which is how often the Plasma widget reads it.
const REFRESH_SECONDS = 30;

// Where a reading turns from green to yellow and from yellow to red, the same
// thresholds src/common/ui/status.py gives status bars.
const WARNING_PERCENT = 50;
const CRITICAL_PERCENT = 80;

// Width of a bar, in pixels before the Shell scales the interface. The fill is
// set in the same unit, so the two scale together.
const BAR_WIDTH = 120;

// Return a service's usages that FORL shows in one place, "in_panel" or "in_tray".
function usagesIn(service, place) {
	return (service.usages || []).filter(usage => usage[place]);
}

// Return the one line the top bar shows, such as "Claude 23% 41%  ChatGPT 12%".
function compactText(services) {
	const parts = [];
	for (const service of services) {
		if (!service.signed_in) {
			continue;
		}
		const shown = usagesIn(service, 'in_tray');
		const usages = shown.length > 0 ? shown : (service.usages || []).slice(0, 1);
		if (usages.length > 0) {
			parts.push(`${service.label} ${usages.map(usage => `${Math.round(usage.percent)}%`).join(' ')}`);
		}
	}
	return parts.length > 0 ? parts.join('  ') : 'FORL';
}

// Return the level of a reading, which names the classes it is colored by.
function levelFor(percent) {
	if (percent >= CRITICAL_PERCENT) {
		return 'critical';
	}
	if (percent >= WARNING_PERCENT) {
		return 'warning';
	}
	return 'ok';
}

// Opacity of a line that only explains, such as "Not signed in", out of 255.
// Set on the label rather than as a color, so it reads in a light or a dark
// Shell alike.
const DIM_OPACITY = 153;

// Return a line of the menu that says something and cannot be chosen, set in
// bold as a heading or dimmed as a remark.
function textItem(text, kind) {
	const item = new PopupMenu.PopupMenuItem(text, {reactive: false, can_focus: false});
	if (kind === 'heading') {
		item.label.add_style_class_name('forl-heading');
	} else {
		item.label.opacity = DIM_OPACITY;
	}
	return item;
}

// Return the row of one usage: its name, a bar and its percentage.
function usageItem(usage) {
	const percent = Math.min(Math.max(Number(usage.percent) || 0, 0), 100);
	const level = levelFor(percent);
	const item = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
	item.add_child(new St.Label({
		text: usage.label,
		x_expand: true,
		y_align: Clutter.ActorAlign.CENTER,
		style_class: 'forl-usage',
	}));
	const track = new St.Widget({style_class: 'forl-bar', y_align: Clutter.ActorAlign.CENTER});
	track.add_child(new St.Widget({
		style_class: `forl-fill forl-fill-${level}`,
		style: `width: ${Math.round(BAR_WIDTH * percent / 100)}px;`,
	}));
	item.add_child(track);
	item.add_child(new St.Label({
		text: `${Math.round(percent)}%`,
		y_align: Clutter.ActorAlign.CENTER,
		style_class: `forl-percent forl-text-${level}`,
	}));
	return item;
}

const ForlIndicator = GObject.registerClass(
class ForlIndicator extends PanelMenu.Button {
	_init() {
		super._init(0.0, 'FORL');
		this._label = new St.Label({text: 'FORL', y_align: Clutter.ActorAlign.CENTER});
		this.add_child(this._label);
		this._services = [];
		this._cancellable = new Gio.Cancellable();
		this._file = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_cache_dir(), 'forl', 'status.json']));
		// FORL replaces the file whole, so a change arrives as a file moved over
		// it; the timer below still catches anything the monitor misses.
		try {
			this._monitor = this._file.monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, null);
			this._monitor.connect('changed', () => this._read());
		} catch (error) {
			this._monitor = null;
		}
		this._timeout = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, REFRESH_SECONDS, () => {
			this._read();
			return GLib.SOURCE_CONTINUE;
		});
		this.connect('destroy', () => this._onDestroy());
		this._render();
		this._read();
	}

	// Read the file again and show what it says.
	async _read() {
		let document;
		try {
			const [contents] = await this._file.load_contents_async(this._cancellable);
			document = JSON.parse(new TextDecoder().decode(contents));
		} catch (error) {
			// No file yet, one being replaced, or the extension turned off:
			// keep what is shown.
			return;
		}
		if (this._cancellable.is_cancelled()) {
			return;
		}
		this._services = Array.isArray(document.services) ? document.services : [];
		this._setHidden(document.tray === true);
		this._render();
	}

	// Step aside while FORL has icons of its own in the top bar.
	_setHidden(hidden) {
		if (hidden) {
			this.menu.close();
		}
		this.container.visible = !hidden;
	}

	// Rebuild the line in the bar and the menu from the last reading.
	_render() {
		this._label.text = compactText(this._services);
		this.menu.removeAll();
		if (this._services.length === 0) {
			this.menu.addMenuItem(textItem('Start FORL to see your usage here.', 'remark'));
			return;
		}
		this._services.forEach((service, index) => {
			if (index > 0) {
				this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
			}
			this.menu.addMenuItem(textItem(service.plan ? `${service.label}  ${service.plan}` : service.label, 'heading'));
			if (!service.signed_in) {
				this.menu.addMenuItem(textItem('Not signed in', 'remark'));
				return;
			}
			for (const usage of usagesIn(service, 'in_panel')) {
				this.menu.addMenuItem(usageItem(usage));
			}
		});
	}

	_onDestroy() {
		this._cancellable.cancel();
		if (this._timeout) {
			GLib.source_remove(this._timeout);
			this._timeout = 0;
		}
		if (this._monitor) {
			this._monitor.cancel();
			this._monitor = null;
		}
	}
});

export default class ForlExtension extends Extension {
	enable() {
		this._indicator = new ForlIndicator();
		Main.panel.addToStatusArea(this.uuid, this._indicator);
	}

	disable() {
		this._indicator?.destroy();
		this._indicator = null;
	}
}
