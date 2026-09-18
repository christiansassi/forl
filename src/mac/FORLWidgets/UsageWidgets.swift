//
//  UsageWidgets.swift
//  The widgets macOS draws on the desktop and in Notification Centre.
//
//  Two sizes, at the shapes macOS gives a widget. The small one is the dial the
//  Dock icon carries with the mark in the corner; the medium one is a row of the
//  panel. Both show the first usage the user chose, because that is what a tile
//  read across a desk has room to say, and the panel is where the rest are.
//

import WidgetKit
import SwiftUI

/// The small widget: a mark in the corner and a dial under it.
struct SmallUsageView: View {
	/// What to draw.
	var entry: UsageEntry

	var body: some View {
		ZStack(alignment: .topLeading) {
			Dial(percent: entry.metric?.percent, accent: entry.accent)
				.frame(maxWidth: .infinity, maxHeight: .infinity)
			ProviderMark(symbolName: entry.symbolName, tint: entry.accent, size: 22)
		}
	}
}

/// The medium widget: a heading and one row of the panel.
struct MediumUsageView: View {
	/// What to draw.
	var entry: UsageEntry

	var body: some View {
		VStack(alignment: .leading, spacing: 0) {
			HStack(spacing: 8) {
				ProviderMark(symbolName: entry.symbolName, tint: entry.accent, size: 16)
				Text(entry.label)
					.font(.system(size: 13, weight: .semibold))
				Spacer()
			}
			Spacer()

			if let metric = entry.metric {
				Text(metric.label)
					.font(.system(size: 13))
					.lineLimit(1)
				HStack(spacing: 10) {
					UsageBar(percent: metric.percent)
					Text(Formatting.percent(metric.percent))
						.font(.system(size: 15, weight: .semibold))
						.monospacedDigit()
				}
				.padding(.top, 6)
				let subtitle = Formatting.subtitle(metric, now: entry.date)
				if !subtitle.isEmpty {
					Text(subtitle)
						.font(.system(size: 11))
						.foregroundStyle(.secondary)
						.lineLimit(2)
						.padding(.top, 4)
				}
			} else {
				Text(entry.message)
					.font(.system(size: 13))
					.foregroundStyle(.secondary)
			}
			Spacer()
		}
	}
}

/// Picks the layout for whichever size macOS is drawing.
struct UsageWidgetView: View {
	/// What to draw.
	var entry: UsageEntry
	/// The size macOS asked for.
	@Environment(\.widgetFamily) private var family

	var body: some View {
		Group {
			switch family {
			case .systemSmall:
				SmallUsageView(entry: entry)
			default:
				MediumUsageView(entry: entry)
			}
		}
		.containerBackground(.fill.tertiary, for: .widget)
	}
}

/// The widget both sizes are configured through.
struct UsageWidget: Widget {
	var body: some WidgetConfiguration {
		AppIntentConfiguration(
			kind: "io.forl.usage",
			intent: SelectServiceIntent.self,
			provider: UsageProvider()
		) { entry in
			UsageWidgetView(entry: entry)
		}
		.configurationDisplayName("Usage")
		.description("How much of your limit you have used. Press Edit Widget to choose the service.")
		.supportedFamilies([.systemSmall, .systemMedium])
	}
}
