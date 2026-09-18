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

	/// Return the color the dial and the mark are drawn in.
	///
	/// - Returns: The provider's accent, or the label color when the entry
	///   belongs to no provider.
	var accent: Color {
		providerKey.flatMap { providerIdentity(for: $0)?.accent } ?? .primary
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
		current(for: configuration.service?.id)
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
			entries: [current(for: configuration.service?.id)],
			policy: .after(Date().addingTimeInterval(pollInterval))
		)
	}

	/// Return the reading the app last wrote, for one service.
	///
	/// - Parameter serviceKey: The service the widget was set to, or nil for
	///   whichever is signed in first.
	/// - Returns: That service's chosen metric, or an entry that says why there
	///   is nothing to show.
	private func current(for serviceKey: String?) -> UsageEntry {
		let state = SharedStore.load()
		let wanted = serviceKey.flatMap { state.reading(for: $0) }
		guard
			let reading = wanted ?? state.readings.first,
			let service = providerIdentity(for: reading.providerKey)
		else {
			let named = serviceKey.flatMap { providerIdentity(for: $0) }
			return UsageEntry(
				date: Date(),
				providerKey: named?.key,
				label: named?.label ?? "FORL",
				symbolName: named?.symbolName ?? "ClaudeMark",
				metric: nil,
				message: named.map { "Open FORL and sign in to \($0.label)." } ?? "Open FORL and sign in."
			)
		}

		let chosen = StoredSelection.keys(for: reading.providerKey)
		let metrics = reading.snapshot?.metrics ?? []
		let metric = chosen.compactMap { key in metrics.first { $0.key == key } }.first ?? metrics.first

		return UsageEntry(
			date: Date(),
			providerKey: reading.providerKey,
			label: service.label,
			symbolName: service.symbolName,
			metric: metric,
			message: reading.signInMessage.isEmpty ? "Loading" : reading.signInMessage
		)
	}
}
