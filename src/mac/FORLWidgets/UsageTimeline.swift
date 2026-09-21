//
//  UsageTimeline.swift
//  Where a widget gets its reading.
//
//  Out of the group container, never off the network. The app polls, writes what
//  it found, and asks WidgetKit to reload; this reads that file back. A widget
//  extension therefore holds no token and makes no request, which is the whole
//  reason the sign-ins stay on the app's side of the container.
//
//  Which service a widget shows is part of its configuration, so two widgets can
//  sit side by side showing different ones.
//

import WidgetKit
import SwiftUI

/// What one widget draws at one moment.
struct UsageEntry: TimelineEntry {
	/// When this entry was made.
	var date: Date
	/// The provider the entry belongs to, or nil when nobody is signed in.
	var providerKey: String?
	/// The product name to show.
	var label: String
	/// The mark to show.
	var symbolName: String
	/// The reading to show, or nil before one has arrived.
	var metric: Metric?
	/// What to say when there is no reading.
	var message: String
	/// Whether the provider is signed in and its first reading is still on its way.
	var loading: Bool = false

	/// Return the color the dial and the mark are drawn in.
	///
	/// - Returns: The provider's accent, or the label color when the entry
	///   belongs to no provider.
	var accent: Color {
		providerKey.flatMap { providerIdentity(for: $0)?.accent } ?? .primary
	}

	/// Resolve a configured reading from one shared snapshot.
	/// - Parameters:
	///   - serviceKey: The selected provider, or nil for the first signed-in provider.
	///   - metricID: A provider-qualified metric identifier, or nil for the session.
	///   - state: The current shared readings.
	/// - Returns: The selected reading or a status message, never another provider's usage.
	static func current(serviceKey: String?, metricID: String?, state: SharedState = SharedStore.load()) -> UsageEntry {
		let key = serviceKey ?? state.readings.first?.providerKey
		let service = key.flatMap(providerIdentity(for:))
		let reading = key.flatMap { state.reading(for: $0) }
		let prefix = key.map { "\($0)/" } ?? ""
		let metricKey = metricID.flatMap { $0.hasPrefix(prefix) ? String($0.dropFirst(prefix.count)) : nil } ?? sessionKey
		let metric = reading?.snapshot?.metrics.first { $0.key == metricKey }
		let message: String
		let loading = reading != nil && reading?.signInMessage.isEmpty == true && reading?.snapshot == nil
		if reading == nil {
			message = service.map { "Open FORL and sign in to \($0.label)." } ?? "Open FORL and sign in."
		} else if let reading, !reading.signInMessage.isEmpty {
			message = reading.signInMessage
		} else if reading?.snapshot == nil {
			message = "Loading"
		} else {
			message = "This reading is unavailable. Edit the widget to choose another."
		}
		return UsageEntry(date: Date(), providerKey: key, label: service?.label ?? "FORL", symbolName: service?.symbolName ?? "ClaudeMark", metric: metric, message: message, loading: loading)
	}
}

/// Reads the shared container for every widget in this bundle.
struct UsageProvider: AppIntentTimelineProvider {
	/// Return what to draw before any reading has been read.
	///
	/// - Parameter context: The widget's context, which this ignores.
	/// - Returns: A placeholder entry.
	func placeholder(in context: Context) -> UsageEntry {
		UsageEntry(
			date: Date(),
			providerKey: "claude",
			label: "Claude",
			symbolName: "ClaudeMark",
			metric: Metric(key: sessionKey, label: sessionLabel, percent: 34, resetsAt: nil, group: .limit),
			message: ""
		)
	}

	/// Return what to draw in the widget gallery.
	///
	/// - Parameters:
	///   - configuration: Which service the widget was set to.
	///   - context: The widget's context, which this ignores.
	/// - Returns: The entry to draw.
	func snapshot(for configuration: SelectServiceIntent, in context: Context) async -> UsageEntry {
		UsageEntry.current(serviceKey: configuration.service?.id, metricID: configuration.metric?.id)
	}

	/// Return the timeline the widget follows.
	///
	/// One entry, and a reload asked for a minute out. The app reloads the
	/// timeline itself after every poll, so the schedule is only what keeps the
	/// widget honest when the app is not running.
	///
	/// - Parameters:
	///   - configuration: Which service the widget was set to.
	///   - context: The widget's context, which this ignores.
	/// - Returns: The timeline to follow.
	func timeline(for configuration: SelectServiceIntent, in context: Context) async -> Timeline<UsageEntry> {
		Timeline(
			entries: [UsageEntry.current(serviceKey: configuration.service?.id, metricID: configuration.metric?.id)],
			policy: .after(Date().addingTimeInterval(pollInterval))
		)
	}

}
