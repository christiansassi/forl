//
//  UsageSnapshot.swift
//  The value objects every surface renders.
//
//  Nothing here knows which provider a reading came from. A provider turns its
//  own response shape into these, and the menu bar, the panel, the Dock and the
//  widgets read only these, which is what lets one interface serve both.
//
//  They are Codable because the app writes the latest reading into the group
//  container and the widget extension reads it back: the widget makes no
//  request of its own and knows no token.
//

import Foundation

/// The key of the window every provider reports.
let sessionKey = "session"
/// The key of the weekly window, for the providers that report one.
let weeklyKey = "weekly"

let sessionLabel = "Current session"
let weeklyLabel = "This week"

/// What a metric key is prefixed with when it names a product rather than a limit.
let productKeyPrefix = "product:"

/// How long the app leaves between readings, in seconds. The widget reads it too,
/// because the timeline it asks the system for is the same length.
let pollInterval: TimeInterval = 60

/// Which of the two groups a metric belongs to.
enum MetricGroup: String, Codable, Sendable {
	case limit
	case product
}

/// One rate limit window and how much of it has been consumed.
struct UsageWindow: Codable, Sendable, Equatable {
	/// Stable identifier of the window, for example "session".
	var key: String
	/// Human readable name shown in the interface.
	var label: String
	/// Share of the window already used, from 0 to 100.
	var percent: Double
	/// Moment the window resets, or nil when the provider omits it.
	var resetsAt: Date?
	/// Name of the model the window is limited to, empty for a window that
	/// covers the whole account.
	var scopeName: String = ""
}

/// A share of the weekly window attributed to one product.
struct BreakdownRow: Codable, Sendable, Equatable {
	/// Stable identifier of the product, for example "claude_code".
	var key: String
	/// Product name, for example "Claude Code".
	var label: String
	/// Share of the weekly window used by that product, 0 to 100.
	var percent: Double
}

/// One number the user can choose to display.
///
/// Limits and products are different things in a response but the same thing to
/// the user, so both are offered through this one shape.
struct Metric: Codable, Sendable, Equatable, Identifiable {
	/// Stable identifier, unique across limits and products.
	var key: String
	/// Name shown in the menu and in the panel.
	var label: String
	/// Share already used, from 0 to 100.
	var percent: Double
	/// Moment the underlying window resets, or nil.
	var resetsAt: Date?
	/// Which group this metric belongs to.
	var group: MetricGroup
	/// What the window covers, empty when it covers the whole account.
	var scopeName: String = ""

	var id: String { key }
}

/// A complete usage reading taken at one moment.
struct UsageSnapshot: Codable, Sendable, Equatable {
	/// When the widget received this reading.
	var fetchedAt: Date
	/// Subscription name to show beside the provider name.
	var plan: String
	/// The session window, which every surface shows unless told otherwise.
	var session: UsageWindow
	/// The weekly account window, or nil when absent.
	var weekly: UsageWindow?
	/// Per model weekly windows.
	var scoped: [UsageWindow] = []
	/// Weekly usage split by product.
	var breakdown: [BreakdownRow] = []
	/// Heading for the extra usage section, empty when there is no such budget.
	var extraLabel: String = ""
	/// Share of that budget spent, or nil when there is none.
	var extraPercent: Double?

	/// Return every limit window, in the order they are offered to the user.
	///
	/// - Returns: The session window first, then the weekly window when present,
	///   then any per model window.
	var windows: [UsageWindow] {
		var ordered = [session]
		if let weekly {
			ordered.append(weekly)
		}
		ordered.append(contentsOf: scoped)
		return ordered
	}

	/// Return everything the user can choose to display, limits then products.
	///
	/// Products are shares of the weekly window, so they inherit that window's
	/// reset time.
	///
	/// - Returns: The limit windows in menu order, then one entry per product of
	///   the weekly breakdown.
	var metrics: [Metric] {
		let weeklyReset = weekly?.resetsAt
		var entries = windows.map { window in
			Metric(
				key: window.key,
				label: window.label,
				percent: window.percent,
				resetsAt: window.resetsAt,
				group: .limit,
				scopeName: window.scopeName
			)
		}
		entries.append(contentsOf: breakdown.map { row in
			Metric(
				key: productKeyPrefix + row.key,
				label: row.label,
				percent: row.percent,
				resetsAt: weeklyReset,
				group: .product
			)
		})
		return entries
	}

	/// Return one displayable metric by key.
	///
	/// - Parameter key: The key of the wanted metric, such as "session".
	/// - Returns: The matching metric, or nil when this reading no longer
	///   reports it, which happens when a scoped limit empties.
	func metric(key: String) -> Metric? {
		metrics.first { $0.key == key }
	}
}

/// Return a usage percentage clamped into the 0 to 100 range.
///
/// Values outside the range are clamped rather than rejected because a provider
/// may report slight overshoot once a limit is exceeded.
///
/// - Parameter value: Percentage reported by a provider, or nil.
/// - Returns: The percentage, between 0 and 100 inclusive, and 0 for nil.
func clampPercent(_ value: Double?) -> Double {
	guard let value, value.isFinite else {
		return 0
	}
	return min(100, max(0, value))
}
