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
	/// A provider that has never been configured shows its session window, which
	/// is the useful thing to show a machine that has just been set up. A
	/// provider whose last reading has been unticked shows none: that is a
	/// choice the user made, and it is a different thing from never having made
	/// one, so the two are stored differently rather than read the same.
	///
	/// - Parameter providerKey: Key of the provider, such as "claude".
	/// - Returns: The chosen keys in the order they were chosen, or the session
	///   window for a provider with no stored choice at all.
	func selected(for providerKey: String) -> [String] {
		StoredSelection.resolve(selection[providerKey])
	}

	/// Add a metric to one provider's selection, or take it away.
	///
	/// Every reading can be unticked. The menu bar keeps an item of the app's own
	/// while none is shown, so there is still a way back to these settings.
	///
	/// - Parameters:
	///   - key: Key of the metric the user clicked.
	///   - providerKey: Key of the provider it belongs to.
	/// - Returns: Nothing.
	func toggle(_ key: String, for providerKey: String) {
		var chosen = selected(for: providerKey)
		if let index = chosen.firstIndex(of: key) {
			chosen.remove(at: index)
		} else {
			chosen.append(key)
		}
		selection[providerKey] = chosen
	}
}

/// What a stored selection means, in one place.
///
/// The app reads it through its observable preferences and anything without the
/// app around it reads the defaults directly, so the rule that turns what was
/// stored into what to show lives here rather than in each of them.
enum StoredSelection {
	/// Return what one provider's stored choice means.
	///
	/// No entry at all is a provider nobody has configured, which shows its
	/// session window. An entry that is empty is a provider whose readings have
	/// all been unticked, which shows none.
	///
	/// - Parameter stored: What was stored for that provider, or nil for none.
	/// - Returns: The metric keys to show.
	static func resolve(_ stored: [String]?) -> [String] {
		stored ?? [sessionKey]
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
