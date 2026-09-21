//
//  Preferences.swift
//  What the app remembers between runs.
//
//  Kept in the shared defaults rather than the app's own, so a widget can read
//  which metric the user chose without being told. Every value has a default
//  that makes sense on a machine that has never been configured, and a stored
//  value that no longer means anything reads as that default, which is what
//  lets the set of choices change without anything having to migrate the file.
//

import Foundation
import Observation

/// What the app remembers, for one provider and for the app as a whole.
@MainActor
@Observable
final class Preferences {
	/// The defaults the app and the widget share.
	private let defaults: UserDefaults

	/// Whether the app starts when the user logs in.
	var startAtLogin: Bool { didSet { defaults.set(startAtLogin, forKey: Key.startAtLogin) } }
	/// Which metrics the user chose to show, keyed by provider.
	var selection: [String: [String]] {
		didSet { defaults.set(selection, forKey: Key.selection) }
	}

	/// The names the values are stored under.
	private enum Key {
		static let startAtLogin = "startAtLogin"
		static let selection = "selection"
	}

	/// Read the stored preferences, falling back to the defaults.
	///
	/// - Parameter defaults: Where to read from, which is the shared suite in
	///   the app and in the widget and a throwaway one in a test.
	/// - Returns: Nothing.
	init(defaults: UserDefaults = .shared) {
		self.defaults = defaults
		startAtLogin = defaults.object(forKey: Key.startAtLogin) as? Bool ?? false
		selection = defaults.object(forKey: Key.selection) as? [String: [String]] ?? [:]
	}

	/// Return the metric keys the user chose for one provider.
	///
	/// - Parameter providerKey: Key of the provider, such as "claude".
	/// - Returns: The chosen keys in the order they were chosen, falling back to
	///   the session window when nothing has been chosen.
	func selected(for providerKey: String) -> [String] {
		let chosen = selection[providerKey] ?? []
		return chosen.isEmpty ? [sessionKey] : chosen
	}

	/// Add a metric to one provider's selection, or take it away.
	///
	/// The last chosen metric cannot be removed, because doing so would leave no
	/// surface to reach the menu from.
	///
	/// - Parameters:
	///   - key: Key of the metric the user clicked.
	///   - providerKey: Key of the provider it belongs to.
	/// - Returns: Nothing.
	func toggle(_ key: String, for providerKey: String) {
		var chosen = selected(for: providerKey)
		if let index = chosen.firstIndex(of: key) {
			guard chosen.count > 1 else {
				return
			}
			chosen.remove(at: index)
		} else {
			chosen.append(key)
		}
		selection[providerKey] = chosen
	}
}

/// The selection, read without the app around it.
///
/// A widget extension draws on whatever thread WidgetKit hands it and has no
/// main actor to wait for, so what it reads is read here rather than through
/// the observable object the app edits.
enum StoredSelection {
	/// Return the metric keys the user chose for one provider.
	///
	/// - Parameters:
	///   - providerKey: Key of the provider, such as "claude".
	///   - defaults: Where to read from.
	/// - Returns: The chosen keys in the order they were chosen, falling back to
	///   the session window when nothing has been chosen.
	static func keys(for providerKey: String, defaults: UserDefaults = .shared) -> [String] {
		let stored = defaults.object(forKey: "selection") as? [String: [String]] ?? [:]
		let chosen = stored[providerKey] ?? []
		return chosen.isEmpty ? [sessionKey] : chosen
	}
}

extension UserDefaults {
	/// The defaults the app and its widget share, falling back to the standard
	/// ones on a build whose App Group entitlement is missing.
	static let shared: UserDefaults = {
		let store = UserDefaults(suiteName: appGroupIdentifier) ?? .standard
		return store
	}()
}
