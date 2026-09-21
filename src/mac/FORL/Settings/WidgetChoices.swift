// Cache the provider's available readings whenever the app publishes an update.

import Foundation

enum WidgetChoices {
	private static let cacheKey = "widgetMetricChoices"

	/// Preserve the last known choices when a provider is temporarily unavailable.
	static func update(from state: SharedState, defaults: UserDefaults = .shared) {
		var cache = defaults.dictionary(forKey: cacheKey) as? [String: [[String: String]]] ?? [:]
		for reading in state.readings {
			guard let metrics = reading.snapshot?.metrics, !metrics.isEmpty else { continue }
			cache[reading.providerKey] = metrics.map { ["key": $0.key, "label": $0.label] }
		}
		defaults.set(cache, forKey: cacheKey)
	}

	/// Return cached choices immediately, with standard choices before the first poll.
	static func available(for providerKey: String, defaults: UserDefaults = .shared) -> [(key: String, label: String)] {
		let cache = defaults.dictionary(forKey: cacheKey) as? [String: [[String: String]]] ?? [:]
		let choices = (cache[providerKey] ?? []).compactMap { entry -> (key: String, label: String)? in
			guard let key = entry["key"], let label = entry["label"], !key.isEmpty, !label.isEmpty else { return nil }
			return (key, label)
		}
		return choices.isEmpty ? [(sessionKey, sessionLabel), (weeklyKey, weeklyLabel)] : choices
	}
}
