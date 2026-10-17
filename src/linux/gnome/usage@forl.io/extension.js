/*
 * The FORL extension for GNOME Shell 45 and later.
 *
 * FORL offers its readings on the session bus as io.forl.Usage, and announces
 * every change, the way the Mac app hands its widgets a reading and asks
 * WidgetKit to redraw them. This extension shows them as GNOME shows its own
 * indicators: in the top bar, each service's mark in the bar's text color with
 * the percentage of each usage chosen for the tray beside it, and on a click, a
 * menu of the Shell's own items with a level bar per usage. Whatever FORL's
 * panel lets the user do, signing in and the settings, opens that panel through
 * the bus, which starts FORL first when it is not running, as a Mac widget
 * opens the app.
 *
 * The extension holds a name of its own, io.forl.Shell, while it is turned on.
 * That is how FORL knows something stands in for a tray, and opens its panel
 * from the top bar rather than as a window of its own.
 *
 * On a GNOME with the AppIndicator extension, FORL already has its own icons
 * in the top bar and says so. The indicator then stays hidden rather than show
 * the same readings twice in the same bar.
 */

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

import {Marks, drawAppMark, foregroundOf} from './icon.js';
import {Panel} from './panel.js';
import {accentHex, interfaceSettings, readingColor} from './theme.js';

// FORL on the session bus, and the name this extension holds there.
const BUS_NAME = 'io.forl.Usage';
const OBJECT_PATH = '/io/forl/Usage';
const INTERFACE = 'io.forl.Usage';
const SHELL_NAME = 'io.forl.Shell';

// Edge of an icon in the top bar, as GNOME sizes its status icons, and the
// space between a mark and its reading and between two services, in pixels
// before the Shell scales the interface.
const ICON_SIZE = 16;
const READING_GAP = 4;
const SERVICE_GAP = 10;

// What separates two readings of one service in the top bar.
const READING_SEPARATOR = ' · ';

// How often the open panel steps its countdown, spinner and skeleton.
const TICK_MILLISECONDS = 50;

// Where FORL keeps the shared artwork inside the extension.
const ASSETS_DIR = 'assets';

const ForlIndicator = GObject.registerClass(
class ForlIndicator extends PanelMenu.Button {
	_init(extensionPath) {
		super._init(0.0, 'FORL');
		this._assetsPath = GLib.build_filenamev([extensionPath, ASSETS_DIR]);
		this._document = {services: []};
		this._settings = interfaceSettings();
		this._settingsChanged = this._settings.connect('changed', () => this._render());

		this._icons = new St.BoxLayout({style: `spacing: ${SERVICE_GAP}px;`});
		this.add_child(this._icons);
		this._marks = new Marks(this._assetsPath);
		this._panel = new Panel(this.menu, this._marks, (service, view) => this._openForl(service, view));
		// The marks take the bar's text color, which is known once the bar has
		// styled the indicator, and changes with the theme.
		this._foreground = '';
		this.connect('style-changed', () => {
			const color = foregroundOf(this);
			const key = `${color.red},${color.green},${color.blue}`;
			if (key !== this._foreground) {
				this._foreground = key;
				this._renderIcons();
			}
		});
		this._tick = 0;
		this.menu.connect('open-state-changed', (_menu, open) => this._onOpenChanged(open));

		this._cancellable = new Gio.Cancellable();
		this._subscription = 0;
		this._connection = null;
		this._ownerId = Gio.bus_own_name(Gio.BusType.SESSION, SHELL_NAME, Gio.BusNameOwnerFlags.NONE, null, null, null);
		this._watchId = Gio.bus_watch_name(
			Gio.BusType.SESSION,
			BUS_NAME,
			Gio.BusNameWatcherFlags.NONE,
			connection => this._onForlAppeared(connection),
			() => this._onForlVanished());
		this.connect('destroy', () => this._onDestroy());
		this._render();
	}

	// FORL is on the bus: follow its announcements and ask for what it has now.
	_onForlAppeared(connection) {
		this._connection = connection;
		if (!this._subscription) {
			this._subscription = connection.signal_subscribe(
				BUS_NAME, INTERFACE, 'StatusChanged', OBJECT_PATH, null, Gio.DBusSignalFlags.NONE,
				(_connection, _sender, _path, _interface, _signal, parameters) => this._show(parameters.deepUnpack()[0]));
		}
		connection.call(
			BUS_NAME, OBJECT_PATH, INTERFACE, 'GetStatus', null, new GLib.VariantType('(s)'),
			Gio.DBusCallFlags.NO_AUTO_START, -1, this._cancellable,
			(source, result) => {
				try {
					this._show(source.call_finish(result).deepUnpack()[0]);
				} catch (error) {
					// FORL left again, or the extension was turned off.
				}
			});
	}

	// FORL has stopped, or crashed: say so at once rather than keep a reading
	// that will not change.
	_onForlVanished() {
		this._document = {running: false, services: []};
		this._setHidden(false);
		this._render();
	}

	// Show a status FORL sent, as JSON.
	_show(status) {
		let document;
		try {
			document = JSON.parse(status);
		} catch (error) {
			return;
		}
		this._document = {...document, running: true};
		this._setHidden(document.tray === true);
		this._render();
	}

	// Ask FORL to open its own panel on a service, in a view. The bus starts
	// FORL for the call when it is not running.
	_openForl(service, view) {
		this.menu.close();
		Gio.DBus.session.call(
			BUS_NAME, OBJECT_PATH, INTERFACE, 'Open', new GLib.Variant('(ss)', [service, view]), null,
			Gio.DBusCallFlags.NONE, -1, null,
			(source, result) => {
				try {
					source.call_finish(result);
				} catch (error) {
					logError(error, 'FORL could not be opened');
				}
			});
	}

	// Step aside while FORL has icons of its own in the top bar.
	_setHidden(hidden) {
		if (hidden) {
			this.menu.close();
		}
		this.container.visible = !hidden;
	}

	// Return the scale the Shell draws the interface at.
	_scale() {
		return St.ThemeContext.get_for_stage(global.stage).scale_factor;
	}

	// Redraw the icons and the menu. The menu is kept filled while it is closed
	// too, since the Shell does not open a menu that has nothing in it.
	_render() {
		this._renderIcons();
		this._renderPanel(false);
	}

	// Put each service someone is signed in to in the bar, as its mark and the
	// readings chosen for the tray, in the order of the tabs, or the app's own
	// icon when there is none, so FORL can always be reached from the bar.
	_renderIcons() {
		this._icons.destroy_all_children();
		const foreground = foregroundOf(this);
		const services = Array.isArray(this._document.services) ? this._document.services : [];
		for (const service of services) {
			const usages = (service.usages || []).filter(entry => entry.in_tray);
			if (!service.signed_in || usages.length === 0) {
				continue;
			}
			const box = new St.BoxLayout({style: `spacing: ${READING_GAP}px;`});
			const mark = this._marks.icon(service.logo, ICON_SIZE, foreground, 'system-status-icon');
			mark.y_align = Clutter.ActorAlign.CENTER;
			box.add_child(mark);
			usages.forEach((usage, index) => {
				const percent = usage.percent;
				const text = percent === null || percent === undefined ? '–' : `${Math.round(percent)}%`;
				const color = percent === null || percent === undefined ? null : readingColor(percent);
				const reading = new St.Label({
					text: index > 0 ? `${READING_SEPARATOR}${text}` : text,
					y_align: Clutter.ActorAlign.CENTER,
					style: color ? `color: ${color};` : '',
				});
				box.add_child(reading);
			});
			this._icons.add_child(box);
		}
		if (this._icons.get_n_children() === 0) {
			const area = new St.DrawingArea({
				style_class: 'system-status-icon',
				y_align: Clutter.ActorAlign.CENTER,
				style: `width: ${ICON_SIZE}px; height: ${ICON_SIZE}px; padding: 0;`,
			});
			area.connect('repaint', () => drawAppMark(area));
			this._icons.add_child(area);
		}
	}

	// Fill the menu, in the accent color the user chose.
	_renderPanel(fromEmpty) {
		this._panel.build(this._document, accentHex(this._settings), this._scale(), fromEmpty);
	}

	// Fill the bars from empty each time the panel opens, as the panel does, and
	// keep the countdown moving while it is open.
	_onOpenChanged(open) {
		if (this._tick) {
			GLib.source_remove(this._tick);
			this._tick = 0;
		}
		if (!open) {
			return;
		}
		this._renderPanel(true);
		this._tick = GLib.timeout_add(GLib.PRIORITY_DEFAULT, TICK_MILLISECONDS, () => {
			this._panel.tick();
			return GLib.SOURCE_CONTINUE;
		});
	}

	_onDestroy() {
		this._cancellable.cancel();
		if (this._tick) {
			GLib.source_remove(this._tick);
			this._tick = 0;
		}
		if (this._subscription) {
			this._connection?.signal_unsubscribe(this._subscription);
			this._subscription = 0;
		}
		if (this._watchId) {
			Gio.bus_unwatch_name(this._watchId);
			this._watchId = 0;
		}
		if (this._ownerId) {
			Gio.bus_unown_name(this._ownerId);
			this._ownerId = 0;
		}
		// The Shell can report the destruction more than once.
		if (this._settings) {
			this._settings.disconnect(this._settingsChanged);
			this._settings = null;
		}
	}
});

export default class ForlExtension extends Extension {
	enable() {
		this._indicator = new ForlIndicator(this.path);
		Main.panel.addToStatusArea(this.uuid, this._indicator);
	}

	disable() {
		this._indicator?.destroy();
		this._indicator = null;
	}
}
