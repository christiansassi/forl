//
//  PanelView.swift
//  The panel that opens from any surface.
//
//  The layout follows Claude's own usage view, and serves ChatGPT just as well:
//  each row puts the name and what it covers on the left, a bar across the
//  middle, and the percentage on the right, with any split by product in its own
//  titled section. A second view carries the settings, reached by the gear at
//  the top right and left by the chevron at the top left.
//
//  Every provider with a sign-in gets its own section, because one app now
//  watches both rather than one process each.
//

import SwiftUI

/// Which of the two views the panel is showing.
enum PanelPage {
	case usage
	case settings
}

/// The whole panel, at whichever page it is on.
struct PanelView: View {
	/// Everything the app is showing.
	@Bindable var store: UsageStore
	/// Which page to draw.
	@State private var page: PanelPage = .usage
	/// Redrawn every second so the countdown in the footer counts down.
	@State private var tick = Date()

	private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

	var body: some View {
		VStack(alignment: .leading, spacing: 0) {
			switch page {
			case .usage:
				usage
			case .settings:
				SettingsView(store: store, onBack: { page = .usage })
			}
		}
		.padding(16)
		.frame(width: 320)
		.onReceive(timer) { tick = $0 }
	}

	/// The reading of every signed-in provider.
	@ViewBuilder
	private var usage: some View {
		HStack(spacing: 8) {
			Text("Usage")
				.font(.system(size: 13, weight: .semibold))
			Spacer()
			Button {
				page = .settings
			} label: {
				Image(systemName: "gearshape")
			}
			.buttonStyle(.plain)
			.help("Settings")
		}
		.padding(.bottom, 14)

		if store.active.isEmpty {
			Text("Sign in to a service in the settings to see its usage here.")
				.font(.system(size: 13))
				.foregroundStyle(.secondary)
				.fixedSize(horizontal: false, vertical: true)
		}

		ForEach(store.active) { state in
			ProviderSection(state: state, now: tick)
			if state.id != store.active.last?.id {
				Divider().opacity(Theme.hairlineOpacity * 8).padding(.vertical, 14)
			}
		}
	}
}

/// One provider's heading, rows and footer.
private struct ProviderSection: View {
	/// The provider to draw.
	var state: ProviderState
	/// The moment the countdown is measured against.
	var now: Date

	var body: some View {
		VStack(alignment: .leading, spacing: 0) {
			HStack(spacing: 8) {
				ProviderMark(symbolName: state.provider.symbolName, tint: state.provider.accent, size: 16)
				Text(state.provider.label)
					.font(.system(size: 13, weight: .semibold))
				if let plan = state.snapshot?.plan, !plan.isEmpty {
					Text(plan)
						.font(.system(size: 11))
						.foregroundStyle(.secondary)
				}
				Spacer()
			}
			.padding(.bottom, 14)

			if let snapshot = state.snapshot {
				ForEach(Array(snapshot.metrics.filter { $0.group == .limit }.enumerated()), id: \.element.id) { index, metric in
					if index > 0 {
						Spacer().frame(height: 14)
					}
					MetricRow(metric: metric, now: now)
				}

				let products = snapshot.metrics.filter { $0.group == .product }
				if !products.isEmpty {
					Divider().opacity(Theme.hairlineOpacity * 8).padding(.vertical, 14)
					Text("This week's usage by product")
						.font(.system(size: 11, weight: .semibold))
						.foregroundStyle(.secondary)
						.padding(.bottom, 8)
					ForEach(Array(products.enumerated()), id: \.element.id) { index, metric in
						if index > 0 {
							Spacer().frame(height: 10)
						}
						MetricRow(metric: metric, now: now)
					}
				}
			}

			Divider().opacity(Theme.hairlineOpacity * 8).padding(.vertical, 14)

			HStack(spacing: 10) {
				Text(state.statusText(interval: pollInterval))
					.font(.system(size: 11))
					.monospacedDigit()
					.foregroundStyle(state.signInMessage.isEmpty ? AnyShapeStyle(.secondary) : AnyShapeStyle(Color.red))
					.fixedSize(horizontal: false, vertical: true)
				Spacer()
				if state.refreshing {
					ProgressView().controlSize(.small)
				}
			}

			if !state.signInLink.isEmpty {
				SignInLink(address: state.signInLink).padding(.top, 12)
			}
		}
	}
}

/// One usage row: a name, a bar and a percentage.
private struct MetricRow: View {
	/// The reading to draw.
	var metric: Metric
	/// The moment the reset sentence is measured against.
	var now: Date

	var body: some View {
		VStack(alignment: .leading, spacing: 2) {
			HStack(spacing: 10) {
				Text(metric.label)
					.font(.system(size: 13))
					.lineLimit(1)
					.frame(width: 138, alignment: .leading)
				UsageBar(percent: metric.percent)
				Text(Formatting.percent(metric.percent))
					.font(.system(size: 13))
					.monospacedDigit()
					.frame(width: 42, alignment: .trailing)
			}
			let subtitle = Formatting.subtitle(metric, now: now)
			if !subtitle.isEmpty {
				Text(subtitle)
					.font(.system(size: 11))
					.foregroundStyle(.secondary)
					.fixedSize(horizontal: false, vertical: true)
			}
		}
	}
}

/// The address a sign-in under way is waiting at.
private struct SignInLink: View {
	/// Where the sign-in is waiting.
	var address: String
	/// Whether the address has been put on the pasteboard yet.
	@State private var copied = false

	var body: some View {
		VStack(alignment: .leading, spacing: 2) {
			Button(address) {
				copy()
			}
			.buttonStyle(.link)
			.lineLimit(1)
			.truncationMode(.middle)

			Text(copied ? "Copied. Paste it in a browser if none opened." : "Click to copy the address.")
				.font(.system(size: 11))
				.foregroundStyle(.secondary)
		}
	}

	/// Put the address on the pasteboard and open it.
	///
	/// Both, rather than one: a browser that opened may have opened behind
	/// something, and an address on the pasteboard can be pasted wherever the
	/// user can see.
	///
	/// - Returns: Nothing.
	private func copy() {
		NSPasteboard.general.clearContents()
		NSPasteboard.general.setString(address, forType: .string)
		copied = true
		if let url = URL(string: address) {
			NSWorkspace.shared.open(url)
		}
	}
}
