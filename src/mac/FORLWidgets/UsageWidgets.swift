//
//  UsageWidgets.swift
//  The widgets macOS draws on the desktop and in Notification Centre.
//
//  Each size shows the provider and reading selected in Edit Widget.
//

import WidgetKit
import SwiftUI

/// The small widget: a number inside an open arc, with the mark in its gap.
struct SmallUsageView: View {
	/// What to draw.
	var entry: UsageEntry

	var body: some View {
		Dial(percent: entry.metric?.percent, accent: entry.accent, symbolName: entry.symbolName)
			.frame(maxWidth: .infinity, maxHeight: .infinity)
			.accessibilityLabel("\(entry.label), \(entry.metric?.label ?? entry.message), \(entry.metric.map { Formatting.percent($0.percent) } ?? "No reading")")
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
						.font(.system(size: 12, weight: .medium))
						.foregroundStyle(.primary.opacity(0.8))
						.lineLimit(2)
						.padding(.top, 5)
				}
			} else if entry.loading {
				SkeletonBlock(width: 96)
				HStack(spacing: 10) {
					UsageBar(percent: nil)
					SkeletonBlock(width: 30, height: 13)
				}
				.padding(.top, 6)
				SkeletonBlock(width: 120)
					.padding(.top, 7)
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
	@Environment(\.widgetContentMargins) private var contentMargins

	var body: some View {
		Group {
			switch family {
			case .systemSmall:
				SmallUsageView(entry: entry)
					.padding(4)
			default:
				MediumUsageView(entry: entry)
					.padding(contentMargins)
			}
		}
		.containerBackground(for: .widget) {
			Theme.widgetBackground
		}
		.widgetURL(URL(string: "forl://provider/\(entry.providerKey ?? "")"))
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
		.description("Choose a provider and a reading in Edit Widget.")
		.supportedFamilies([.systemSmall, .systemMedium])
		.contentMarginsDisabled()
		.containerBackgroundRemovable(false)
	}
}
