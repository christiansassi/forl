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
	/// Whether the panel names the plan, such as "Max 5x", beside the service.
	var showPlan: Bool { didSet { defaults.set(showPlan, forKey: Key.showPlan) } }
	/// Which metrics the user chose to show, keyed by provider.
	var selection: [String: [String]] {
		didSet { defaults.set(selection, forKey: Key.selection) }
	}
	/// Which metrics the user chose to see in the panel, keyed by provider.
	var panelSelection: [String: [String]] {
		didSet { defaults.set(panelSelection, forKey: Key.panelSelection) }
	}

	/// The names the values are stored under.
	private enum Key {
		static let startAtLogin = "startAtLogin"
		static let showPlan = "showPlan"
		static let selection = "selection"
		static let panelSelection = "panelSelection"
	}

	/// Read the stored preferences, falling back to the defaults.
	///
	/// - Parameter defaults: Where to read from, which is the shared suite in
	///   the app and in the widget and a throwaway one in a test.
	/// - Returns: Nothing.
	init(defaults: UserDefaults = .shared) {
		self.defaults = defaults
		startAtLogin = defaults.object(forKey: Key.startAtLogin) as? Bool ?? false
		// On unless turned off, since the plan is what every percentage is a
		// percentage of.
		showPlan = defaults.object(forKey: Key.showPlan) as? Bool ?? true
		selection = defaults.object(forKey: Key.selection) as? [String: [String]] ?? [:]
		panelSelection = defaults.object(forKey: Key.panelSelection) as? [String: [String]] ?? [:]
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
		selection[providerKey] = Self.toggled(key, in: selected(for: providerKey))
	}

	/// Return the metric keys one provider's panel shows.
	///
	/// A provider that has never been configured shows its session and weekly
	/// windows, which are the two every plan has; the rest are a tick away. As
	/// with the menu bar, a panel whose every reading has been unticked shows
	/// none rather than falling back to the default.
	///
	/// - Parameter providerKey: Key of the provider, such as "claude".
	/// - Returns: The chosen keys, or the session and weekly windows for a
	///   provider with no stored choice at all.
	func panelShown(for providerKey: String) -> [String] {
		panelSelection[providerKey] ?? [sessionKey, weeklyKey]
	}

	/// Add a metric to one provider's panel, or take it away.
	///
	/// - Parameters:
	///   - key: Key of the metric the user clicked.
	///   - providerKey: Key of the provider it belongs to.
	/// - Returns: Nothing.
	func togglePanel(_ key: String, for providerKey: String) {
		panelSelection[providerKey] = Self.toggled(key, in: panelShown(for: providerKey))
	}

	/// Return a list of metric keys with one added at the end, or taken out.
	///
	/// - Parameters:
	///   - key: The metric to add or take out.
	///   - chosen: The keys as they stand.
	/// - Returns: The keys without `key` when it was there, with it at the end
	///   when it was not.
	private static func toggled(_ key: String, in chosen: [String]) -> [String] {
		var next = chosen
		if let index = next.firstIndex(of: key) {
			next.remove(at: index)
		} else {
			next.append(key)
		}
		return next
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
