/*
 * The FORL extension for GNOME Shell 45 and later.
 *
 * FORL offers its readings on the session bus as io.forl.Usage, and announces
 * every change, the way the Mac app hands its widgets a reading and asks
 * WidgetKit to redraw them. This extension shows them the way FORL shows them
 * where it has a tray: in the top bar, one icon per usage chosen for the tray,
 * drawn as the tray icons are, and on a click, the panel, laid out as the panel
 * is. Whatever the panel lets the user do, signing in and the settings, opens
 * FORL's own panel through the bus, which starts FORL first when it is not
 * running, as a Mac widget opens the app.
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

import {drawAppMark, drawIcon} from './icon.js';
import {Panel} from './panel.js';
import {currentPalette, interfaceSettings} from './theme.js';

// FORL on the session bus, and the name this extension holds there.
const BUS_NAME = 'io.forl.Usage';
const OBJECT_PATH = '/io/forl/Usage';
const INTERFACE = 'io.forl.Usage';
const SHELL_NAME = 'io.forl.Shell';

// Edge of an icon in the top bar, and the space between two of them, in pixels
// before the Shell scales the interface.
const ICON_SIZE = 16;
const ICON_GAP = 6;

// How often the open panel steps its countdown, spinner and skeleton.
const TICK_MILLISECONDS = 50;

// Where FORL keeps the shared artwork inside the extension.
const ASSETS_DIR = 'assets';

// The panel's surface, with the padding the panel keeps around its content.
const PANEL_PAD = 20;

const ForlIndicator = GObject.registerClass(
class ForlIndicator extends PanelMenu.Button {
	_init(extensionPath) {
		super._init(0.0, 'FORL');
		this._assetsPath = GLib.build_filenamev([extensionPath, ASSETS_DIR]);
		this._document = {services: []};
		this._settings = interfaceSettings();
		this._settingsChanged = this._settings.connect('changed', () => this._render());

		this._icons = new St.BoxLayout({style: `spacing: ${ICON_GAP}px;`});
		this.add_child(this._icons);
		this._panel = new Panel(this._assetsPath, (service, view) => this._openForl(service, view));
		this.menu.box.add_child(this._panel.actor);
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

	// Redraw the icons, and the panel when it is open.
	_render() {
		this._renderIcons();
		if (this.menu.isOpen) {
			this._renderPanel(false);
		}
	}

	// Put one icon in the bar per usage chosen for the tray, in the order of the
	// tabs, or the app's own icon when there is none, so FORL can always be
	// reached from the bar. Clicking a service's icon opens the panel on it.
	_renderIcons() {
		this._icons.destroy_all_children();
		const family = this._settings.get_string('font-name');
		const services = Array.isArray(this._document.services) ? this._document.services : [];
		for (const service of services) {
			if (!service.signed_in) {
				continue;
			}
			for (const usage of (service.usages || []).filter(entry => entry.in_tray)) {
				const area = new St.DrawingArea({
					reactive: true,
					y_align: Clutter.ActorAlign.CENTER,
					style: `width: ${ICON_SIZE}px; height: ${ICON_SIZE}px;`,
				});
				area.connect('repaint', () => {
					const cr = area.get_context();
					const [width, height] = area.get_surface_size();
					drawIcon(cr, Math.min(width, height), usage.percent, service.accent, family);
					cr.$dispose();
				});
				area.connect('button-press-event', () => {
					this._panel.select(service.key);
					return Clutter.EVENT_PROPAGATE;
				});
				this._icons.add_child(area);
			}
		}
		if (this._icons.get_n_children() === 0) {
			const area = new St.DrawingArea({
				y_align: Clutter.ActorAlign.CENTER,
				style: `width: ${ICON_SIZE}px; height: ${ICON_SIZE}px;`,
			});
			area.connect('repaint', () => {
				const cr = area.get_context();
				const [width, height] = area.get_surface_size();
				drawAppMark(cr, Math.min(width, height));
				cr.$dispose();
			});
			this._icons.add_child(area);
		}
	}

	// Lay the panel out on its own surface, in the app mode the user chose.
	_renderPanel(fromEmpty) {
		const palette = currentPalette(this._settings);
		this.menu.box.set_style(`background-color: ${palette.surface}; padding: ${PANEL_PAD}px;`);
		this._panel.build(this._document, palette, this._scale(), fromEmpty);
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
