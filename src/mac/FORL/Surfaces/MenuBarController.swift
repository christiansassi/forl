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
	/// What each item was last dressed with, keyed the same way.
	private var dressed: [String: Appearance] = [:]
	/// The menu every item opens, built once.
	private lazy var menu: NSMenu = buildMenu()

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
			for metric in state.displayed(store.preferences) {
				let identifier = "\(state.provider.key)/\(metric.key)"
				wanted.append(identifier)
				dress(identifier: identifier, state: state, metric: metric)
			}
		}

		// Nothing ticked, or nobody signed in: the app keeps one item of its own
		// rather than leaving the bar, which is the only way back to the panel
		// and so to the settings that put the readings back.
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
		let appearance = Appearance(percent: nil, symbolName: "", accent: .primary, title: "", tooltip: "FORL")
		let item = items[emptyIdentifier] ?? create(identifier: emptyIdentifier)
		guard let button = item.button, dressed[emptyIdentifier] != appearance else {
			return
		}
		button.image = MenuBarIcon.appIcon()
		button.image?.accessibilityDescription = "FORL"
		button.imagePosition = .imageOnly
		button.attributedTitle = NSAttributedString(string: "")
		button.toolTip = appearance.tooltip
		dressed[emptyIdentifier] = appearance
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
			tooltip: metric.map { state.tooltip(for: $0) } ?? state.statusText(interval: pollInterval)
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
		dressed.removeValue(forKey: identifier)
	}

	/// Return the menu every item opens.
	///
	/// A right click offers the way out of the app and nothing else. Which
	/// readings the bar shows is chosen in the settings, beside everything else
	/// the user chooses, rather than in a menu that would say it a second time.
	///
	/// - Returns: The menu, which never changes.
	private func buildMenu() -> NSMenu {
		let menu = NSMenu()
		// The app is not the active one, so its menu would otherwise be asked to
		// validate its items against somebody else's responder chain.
		menu.autoenablesItems = false
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
		menu.popUp(positioning: nil, at: NSPoint(x: 0, y: sender.bounds.height), in: sender)
	}
}
