//
//  MenuBarController.swift
//  The menu bar items, one per usage the user chose.
//
//  Every item carries its provider's mark, usage bar and percentage.
//
//  A click opens the panel. A right click opens a menu of every usage the
//  account reports, so the selection can be changed without going to the
//  settings first.
//
//  There is always at least one item, even with nobody signed in. An app whose
//  only way in is a menu bar item cannot afford to have none: the item that is
//  left says so and opens the panel, which is where signing in happens.
//

import AppKit
import SwiftUI

/// The space between the tank and the percentage, as a leading space on the
/// title. The button lays the image and the title out itself and leaves them
/// touching.
private let titleLead = " "

/// The name of the one item shown when nobody is signed in.
private let emptyIdentifier = "forl/none"

/// Everything one item shows, so a redraw can tell whether anything changed.
///
/// The surfaces are rebuilt on a timer rather than observed value by value, and
/// an item rebuilt while the pointer is dragging it loses the drag: a new image
/// resizes a variable length item, and the item goes back where it started. So
/// nothing is assigned to a button whose reading has not moved.
private struct Appearance: Equatable {
	/// The reading the icon is drawn at, or nil before one arrives.
	var percent: Double?
	/// Name of the provider mark in the icon.
	var symbolName: String
	/// The color the icon is drawn in.
	var accent: Color
	/// The text beside the icon.
	var title: String
	/// What the item says on hover.
	var tooltip: String
	/// The readings the item's menu offers.
	var menu: [MenuEntry]
}

/// One line of the menu an item opens.
private struct MenuEntry: Equatable {
	/// What the line says.
	var label: String
	/// The provider and metric the line stands for.
	var identifier: String
	/// Whether the reading is one of those shown in the bar.
	var chosen: Bool
	/// Whether a separator follows the line.
	var endsGroup: Bool
}

/// The set of menu bar items, kept in step with what the user chose.
@MainActor
final class MenuBarController {
	/// Everything the app is showing.
	private let store: UsageStore
	/// Called when an item is clicked, with the button to open the panel under.
	private let onActivate: (NSStatusBarButton) -> Void

	/// The items on screen, keyed by provider and metric.
	private var items: [String: NSStatusItem] = [:]
	/// The menu each item opens, rebuilt whenever a reading arrives.
	private var menus: [String: NSMenu] = [:]
	/// What each item was last dressed with, keyed the same way.
	private var dressed: [String: Appearance] = [:]

	/// Build the controller with no items showing yet.
	///
	/// - Parameters:
	///   - store: Everything the app is showing.
	///   - onActivate: Called when an item is clicked.
	/// - Returns: Nothing.
	init(store: UsageStore, onActivate: @escaping (NSStatusBarButton) -> Void) {
		self.store = store
		self.onActivate = onActivate
	}

	/// Make the items in the bar match what the user chose.
	///
	/// - Returns: Nothing.
	func sync() {
		var wanted: [String] = []
		for state in store.active {
			let metrics = state.displayed(store.preferences)
			for metric in metrics {
				let identifier = "\(state.provider.key)/\(metric.key)"
				wanted.append(identifier)
				dress(identifier: identifier, state: state, metric: metric)
			}
			if metrics.isEmpty {
				let identifier = "\(state.provider.key)/"
				wanted.append(identifier)
				dress(identifier: identifier, state: state, metric: nil)
			}
		}

		if wanted.isEmpty {
			wanted.append(emptyIdentifier)
			dressEmpty()
		}

		for identifier in items.keys where !wanted.contains(identifier) {
			retire(identifier)
		}
	}

	/// Take every item out of the bar.
	///
	/// - Returns: Nothing.
	func clear() {
		for identifier in items.keys {
			retire(identifier)
		}
	}

	/// Return the button of the first item, which the panel opens under.
	///
	/// - Returns: The button, or nil when no item is in the bar.
	func firstButton() -> NSStatusBarButton? {
		items.keys.sorted().compactMap { items[$0]?.button }.first
	}

	/// Put the one item that stands for an app nobody has signed in to.
	///
	/// - Returns: Nothing.
	private func dressEmpty() {
		let appearance = Appearance(percent: nil, symbolName: "", accent: .primary, title: "", tooltip: "FORL: not signed in", menu: [])
		let item = items[emptyIdentifier] ?? create(identifier: emptyIdentifier)
		guard let button = item.button, dressed[emptyIdentifier] != appearance else {
			return
		}
		button.image = NSImage(
			systemSymbolName: "gauge.with.dots.needle.bottom.50percent",
			accessibilityDescription: "FORL"
		)
		button.imagePosition = .imageOnly
		button.attributedTitle = NSAttributedString(string: "")
		button.toolTip = appearance.tooltip
		menus[emptyIdentifier] = emptyMenu()
		dressed[emptyIdentifier] = appearance
	}

	/// Return the menu that item opens.
	///
	/// - Returns: A menu with nothing to choose between and a way out, which is
	///   all there is to offer before anyone has signed in.
	private func emptyMenu() -> NSMenu {
		let menu = NSMenu()
		menu.autoenablesItems = false
		let quit = NSMenuItem(title: "Quit FORL", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
		quit.target = NSApp
		quit.isEnabled = true
		menu.addItem(quit)
		return menu
	}

	/// Put one reading on one item, creating the item when it is new.
	///
	/// - Parameters:
	///   - identifier: The provider and metric the item stands for.
	///   - state: The provider the reading belongs to.
	///   - metric: The reading, or nil before one has arrived.
	/// - Returns: Nothing.
	private func dress(identifier: String, state: ProviderState, metric: Metric?) {
		let appearance = Appearance(
			percent: metric?.percent,
			symbolName: state.provider.symbolName,
			accent: state.provider.accent,
			title: titleLead + (metric.map { Formatting.percent($0.percent) } ?? "-"),
			tooltip: metric.map { state.tooltip(for: $0) } ?? state.statusText(interval: pollInterval),
			menu: menuEntries(for: state)
		)
		let item = items[identifier] ?? create(identifier: identifier)
		guard let button = item.button, dressed[identifier] != appearance else {
			return
		}

		button.image = MenuBarIcon.image(
			percent: appearance.percent,
			accent: appearance.accent,
			symbolName: appearance.symbolName
		)
		button.imagePosition = .imageLeft
		button.attributedTitle = NSAttributedString(
			string: appearance.title,
			attributes: [
				.font: NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .medium),
				.foregroundColor: NSColor.labelColor,
			]
		)
		button.toolTip = appearance.tooltip
		menus[identifier] = buildMenu(from: appearance.menu)
		dressed[identifier] = appearance
	}

	/// Put one item in the bar and wire its clicks up.
	///
	/// - Parameter identifier: The provider and metric the item stands for.
	/// - Returns: The new item.
	private func create(identifier: String) -> NSStatusItem {
		let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
		// Named so the user can drag the items into the order they want and have
		// that order survive a restart.
		item.autosaveName = "forl-\(identifier)"
		if let button = item.button {
			button.target = self
			button.action = #selector(clicked(_:))
			button.sendAction(on: [.leftMouseUp, .rightMouseUp])
			button.identifier = NSUserInterfaceItemIdentifier(identifier)
		}
		items[identifier] = item
		return item
	}

	/// Take one item out of the bar.
	///
	/// - Parameter identifier: The provider and metric whose item should go.
	/// - Returns: Nothing.
	private func retire(_ identifier: String) {
		if let item = items.removeValue(forKey: identifier) {
			NSStatusBar.system.removeStatusItem(item)
		}
		menus.removeValue(forKey: identifier)
		dressed.removeValue(forKey: identifier)
	}

	/// Return what one service's menu says.
	///
	/// - Parameter state: The provider the menu belongs to.
	/// - Returns: One line per usage the service reports, grouped as the panel groups them.
	private func menuEntries(for state: ProviderState) -> [MenuEntry] {
		let chosen = Set(store.preferences.selected(for: state.provider.key))
		var entries: [MenuEntry] = []
		for group in [MetricGroup.limit, .product] {
			let metrics = state.snapshot?.metrics.filter { $0.group == group } ?? []
			guard !metrics.isEmpty else {
				continue
			}
			for metric in metrics {
				entries.append(MenuEntry(
					label: metric.label,
					identifier: "\(state.provider.key)/\(metric.key)",
					chosen: chosen.contains(metric.key),
					endsGroup: metric.id == metrics.last?.id
				))
			}
		}
		return entries
	}

	/// Return the menu those lines make.
	///
	/// - Parameter entries: The readings the menu offers, in the order shown.
	/// - Returns: The menu, ending in the way out of the app.
	private func buildMenu(from entries: [MenuEntry]) -> NSMenu {
		let menu = NSMenu()
		// The app is not the active one, so its menu would otherwise be asked to
		// validate its items against somebody else's responder chain.
		menu.autoenablesItems = false

		for entry in entries {
			let item = NSMenuItem(title: entry.label, action: #selector(chose(_:)), keyEquivalent: "")
			item.target = self
			item.representedObject = entry.identifier
			item.state = entry.chosen ? .on : .off
			item.isEnabled = true
			menu.addItem(item)
			if entry.endsGroup {
				menu.addItem(.separator())
			}
		}

		let quit = NSMenuItem(title: "Quit FORL", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
		quit.target = NSApp
		quit.isEnabled = true
		menu.addItem(quit)
		return menu
	}

	/// Act on a click on any of the items.
	///
	/// A click with the control key held is how a one button mouse asks for a
	/// menu, and macOS reports it as an ordinary click with a modifier rather
	/// than as a right one, so both are counted the same way.
	///
	/// - Parameter sender: The button that was clicked.
	/// - Returns: Nothing.
	@objc private func clicked(_ sender: NSStatusBarButton) {
		let event = NSApp.currentEvent
		// Command belongs to the menu bar, not to this app: it is how an item is
		// dragged into another place in the bar, and opening the panel on the way
		// out of that drag would fight it.
		guard event?.modifierFlags.contains(.command) != true else {
			return
		}
		let wantsMenu = event?.type == .rightMouseUp
			|| event?.modifierFlags.contains(.control) == true

		guard wantsMenu else {
			if let key = sender.identifier?.rawValue.split(separator: "/").first {
				NotificationCenter.default.post(name: .forlSelectProvider, object: String(key))
			}
			onActivate(sender)
			return
		}
		guard
			let identifier = sender.identifier?.rawValue,
			let menu = menus[identifier]
		else {
			return
		}
		menu.popUp(positioning: nil, at: NSPoint(x: 0, y: sender.bounds.height), in: sender)
	}

	/// Add the usage the user picked to the menu bar, or take it away.
	///
	/// - Parameter sender: The menu item that was picked.
	/// - Returns: Nothing.
	@objc private func chose(_ sender: NSMenuItem) {
		guard
			let identifier = sender.representedObject as? String,
			let slash = identifier.firstIndex(of: "/")
		else {
			return
		}
		let providerKey = String(identifier[identifier.startIndex..<slash])
		let metricKey = String(identifier[identifier.index(after: slash)...])
		store.preferences.toggle(metricKey, for: providerKey)
		store.publish()
		sync()
	}
}
