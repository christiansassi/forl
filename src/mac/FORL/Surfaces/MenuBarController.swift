//
//  MenuBarController.swift
//  The menu bar items, one per usage the user chose.
//
//  Each item is a tank in the color of the reading with the percentage beside
//  it, and the first item of each service carries that service's mark, which
//  labels the whole run: several items of one service sit together, so
//  repeating the mark on each would only take width from the bar.
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
		guard store.preferences.menuBar else {
			clear()
			return
		}

		var wanted: [String] = []
		for state in store.active {
			let metrics = state.displayed(store.preferences)
			for (index, metric) in metrics.enumerated() {
				let identifier = "\(state.provider.key)/\(metric.key)"
				wanted.append(identifier)
				dress(identifier: identifier, state: state, metric: metric, leading: index == 0)
			}
			if metrics.isEmpty {
				let identifier = "\(state.provider.key)/"
				wanted.append(identifier)
				dress(identifier: identifier, state: state, metric: nil, leading: true)
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
		let item = items[emptyIdentifier] ?? create(identifier: emptyIdentifier)
		guard let button = item.button else {
			return
		}
		button.image = NSImage(
			systemSymbolName: "gauge.with.dots.needle.bottom.50percent",
			accessibilityDescription: "FORL"
		)
		button.imagePosition = .imageOnly
		button.attributedTitle = NSAttributedString(string: "")
		button.toolTip = "FORL: not signed in"
		menus[emptyIdentifier] = emptyMenu()
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
	///   - leading: Whether this is the first item of its service, which is the
	///     one that carries the mark.
	/// - Returns: Nothing.
	private func dress(identifier: String, state: ProviderState, metric: Metric?, leading: Bool) {
		let item = items[identifier] ?? create(identifier: identifier)
		guard let button = item.button else {
			return
		}

		let compact = store.preferences.menuBarStyle == .compact
		button.image = MenuBarIcon.image(
			percent: metric?.percent,
			accent: leading && !compact ? state.provider.accent : nil,
			symbolName: leading && !compact ? state.provider.symbolName : nil
		)
		button.imagePosition = .imageLeft
		button.attributedTitle = NSAttributedString(
			string: titleLead + (metric.map { Formatting.percent($0.percent) } ?? "-"),
			attributes: [
				.font: NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .medium),
				.foregroundColor: NSColor.labelColor,
			]
		)
		button.toolTip = metric.map { state.tooltip(for: $0) } ?? state.statusText(interval: pollInterval)
		menus[identifier] = buildMenu(for: state)
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
	}

	/// Return the menu one service's items open.
	///
	/// - Parameter state: The provider the menu belongs to.
	/// - Returns: A menu of that service's usages, then the settings and quit.
	private func buildMenu(for state: ProviderState) -> NSMenu {
		let menu = NSMenu()
		// The app is not the active one, so its menu would otherwise be asked to
		// validate its items against somebody else's responder chain.
		menu.autoenablesItems = false

		let chosen = Set(store.preferences.selected(for: state.provider.key))
		for group in [MetricGroup.limit, .product] {
			let entries = state.snapshot?.metrics.filter { $0.group == group } ?? []
			guard !entries.isEmpty else {
				continue
			}
			for metric in entries {
				let item = NSMenuItem(title: metric.label, action: #selector(chose(_:)), keyEquivalent: "")
				item.target = self
				item.representedObject = "\(state.provider.key)/\(metric.key)"
				item.state = chosen.contains(metric.key) ? .on : .off
				item.isEnabled = true
				menu.addItem(item)
			}
			menu.addItem(.separator())
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
		let wantsMenu = event?.type == .rightMouseUp
			|| event?.modifierFlags.contains(.control) == true

		guard wantsMenu else {
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
