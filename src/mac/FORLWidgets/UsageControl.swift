//
//  UsageControl.swift
//  The Control Center control.
//
//  The same reading as the widgets, at the one size Control Center gives: a
//  symbol, a name and a value. Clicking it opens the app, which is where the
//  panel and the settings are.
//
//  Control Center takes controls from other applications only on macOS 26, where
//  one can also be dragged out of Control Center and dropped on the menu bar,
//  which is why this is worth having beside the menu bar items the app puts
//  there itself. On an earlier system the app simply offers the widgets and no
//  control, rather than refusing to run.
//

import AppKit
import WidgetKit
import SwiftUI

/// The reading, as Control Center shows it.
@available(macOS 26.0, *)
struct UsageControl: ControlWidget {
	var body: some ControlWidgetConfiguration {
		StaticControlConfiguration(kind: "io.forl.control") {
			ControlWidgetButton(action: OpenFORLIntent()) {
				Label {
					Text(ControlReading.current().title)
				} icon: {
					Image(systemName: "gauge.with.dots.needle.bottom.50percent")
				}
				Text(ControlReading.current().detail)
			}
		}
		.displayName("Usage")
		.description("How much of your current limit you have used.")
	}
}

/// What the control says, read from the same container the widgets read.
enum ControlReading {
	/// Return the line and the detail the control shows.
	///
	/// - Returns: The percentage and which limit it is, or a line saying nobody
	///   is signed in.
	static func current() -> (title: String, detail: String) {
		let state = SharedStore.load()
		guard
			let reading = state.readings.first,
			let service = providerIdentity(for: reading.providerKey),
			let snapshot = reading.snapshot
		else {
			return ("FORL", "Not signed in")
		}
		let chosen = StoredSelection.keys(for: reading.providerKey)
		let metric = chosen.compactMap { key in snapshot.metrics.first { $0.key == key } }.first
			?? snapshot.metrics.first
		guard let metric else {
			return (service.label, "No reading")
		}
		return (Formatting.percent(metric.percent), "\(service.label) \(metric.label.lowercased())")
	}
}
