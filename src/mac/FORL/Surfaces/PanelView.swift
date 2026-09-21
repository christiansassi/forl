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
	/// Resize the panel when its page or provider readings change height.
	var onHeightChange: (CGFloat) -> Void
	/// Which page to draw.
	@State private var page: PanelPage = .usage
	@State private var selectedProviderKey = providerIdentities.sorted { $0.label < $1.label }.first?.key ?? "claude"
	/// Redrawn every second so the countdown in the footer counts down.
	@State private var tick = Date()

	private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

	var body: some View {
		ScrollView(.vertical) {
			VStack(alignment: .leading, spacing: 0) {
				ProviderTabs(selectedKey: $selectedProviderKey)
					.padding(.bottom, 14)
				if let state = store.state(for: selectedProviderKey), !state.signedIn {
					signIn(state: state)
				} else {
					switch page {
					case .usage:
						usage(for: selectedProviderKey)
					case .settings:
						SettingsView(store: store, selectedProviderKey: $selectedProviderKey, onBack: { page = .usage })
					}
				}
			}
			.padding(16)
			.frame(width: 320)
			.fixedSize(horizontal: false, vertical: true)
			.onGeometryChange(for: CGFloat.self) { geometry in
				geometry.size.height
			} action: { height in
				onHeightChange(height)
			}
		}
		.defaultScrollAnchor(.top)
		.frame(width: 320)
		.frame(maxHeight: .infinity, alignment: .top)
		.onReceive(timer) { tick = $0 }
		.onReceive(NotificationCenter.default.publisher(for: .forlSelectProvider)) { notification in
			if let key = notification.object as? String, providerIdentity(for: key) != nil {
				selectedProviderKey = key
				page = .usage
			}
		}
	}

	/// Offer sign-in directly for the selected provider before showing its settings.
	/// - Parameter state: The provider awaiting authentication.
	/// - Returns: The provider-colored action and any authentication status.
	private func signIn(state: ProviderState) -> some View {
		VStack(spacing: 12) {
			Button {
				Task {
					await state.signIn()
					page = .usage
					store.publish()
					store.refresh()
				}
			} label: {
				Text(state.signingIn ? "Signing in…" : "Sign in to \(state.provider.label)")
					.font(.system(size: 14, weight: .semibold))
					.foregroundStyle(state.provider.accent)
					.frame(maxWidth: .infinity, minHeight: 44)
					.contentShape(Rectangle())
			}
			.buttonStyle(.plain)
			.disabled(state.signingIn)
			if !state.signingIn, !state.signInMessage.isEmpty, state.signInMessage != "Signed out." {
				Text(state.signInMessage)
					.font(.system(size: 11))
					.foregroundStyle(.secondary)
					.fixedSize(horizontal: false, vertical: true)
			}
			if !state.signInLink.isEmpty {
				SignInLink(address: state.signInLink)
			}
		}
		.padding(.vertical, 12)
	}

	/// The reading of every signed-in provider.
	@ViewBuilder
	private func usage(for providerKey: String) -> some View {
		HStack(spacing: 8) {
			if let provider = providerIdentity(for: providerKey) {
				ProviderMark(symbolName: provider.symbolName, tint: provider.accent, size: 16)
				Text(provider.label)
					.font(.system(size: 13, weight: .semibold))
			}
			if let plan = store.state(for: providerKey)?.snapshot?.plan, !plan.isEmpty {
				Text(plan)
					.font(.system(size: 11))
					.foregroundStyle(.secondary)
			}
			Spacer()
			SettingsButton(accent: providerIdentity(for: providerKey)?.accent ?? .accentColor) {
				page = .settings
			}
		}
		.padding(.bottom, 14)

		if let state = store.state(for: providerKey), state.signedIn {
			ProviderSection(state: state, now: tick)
		} else {
			Text("Sign in to a service in the settings to see its usage here.")
				.font(.system(size: 13))
				.foregroundStyle(.secondary)
				.fixedSize(horizontal: false, vertical: true)
		}

	}
}

extension Notification.Name {
	static let forlSelectProvider = Notification.Name("forlSelectProvider")
}

/// The gear that opens the settings.
private struct SettingsButton: View {
	/// The color the gear takes while the pointer is over it.
	var accent: Color
	/// Called when the gear is clicked.
	var action: () -> Void
	/// Whether the pointer is over the gear.
	@State private var hovering = false

	var body: some View {
		Button(action: action) {
			// Trailing, so the gear ends where the percentages in the rows below do
			// rather than in the middle of a box that reaches past them.
			Image(systemName: "gearshape.fill")
				.frame(width: 28, height: 28, alignment: .trailing)
				.contentShape(Rectangle())
		}
		.buttonStyle(.plain)
		.foregroundStyle(hovering ? AnyShapeStyle(accent) : AnyShapeStyle(.secondary))
		.onHover { hovering = $0 }
		.help("Settings")
	}
}

/// Switch between providers without leaving the panel.
private struct ProviderTabs: View {
	@Binding var selectedKey: String
	private let providers = providerIdentities.sorted { $0.label < $1.label }

	var body: some View {
			HStack(spacing: 4) {
				ForEach(providers, id: \.key) { provider in
					Button {
						selectedKey = provider.key
					} label: {
						HStack(spacing: 6) {
							ProviderMark(symbolName: provider.symbolName, tint: provider.accent, size: 14)
							Text(provider.label)
								.font(.system(size: 12, weight: selectedKey == provider.key ? .semibold : .regular))
								.lineLimit(1)
						}
						.frame(maxWidth: .infinity)
						.padding(.vertical, 7)
						.contentShape(Rectangle())
					}
					.buttonStyle(.plain)
					.foregroundStyle(selectedKey == provider.key ? AnyShapeStyle(provider.accent) : AnyShapeStyle(.secondary))
					.background {
						RoundedRectangle(cornerRadius: 7, style: .continuous)
							.fill(selectedKey == provider.key ? provider.accent.opacity(0.14) : Color.clear)
					}
					.overlay {
						RoundedRectangle(cornerRadius: 7, style: .continuous)
							.stroke(selectedKey == provider.key ? provider.accent.opacity(0.35) : Color.clear, lineWidth: 1)
					}
			}
		}
		.frame(maxWidth: .infinity)
	}
}

/// One provider's heading, rows and footer.
private struct ProviderSection: View {
	/// The provider to draw.
	var state: ProviderState
	/// The moment the countdown is measured against.
	var now: Date

	/// Whether the first reading of this provider is still on its way.
	private var loading: Bool {
		state.snapshot == nil && state.signInMessage.isEmpty
	}

	var body: some View {
		VStack(alignment: .leading, spacing: 0) {
			if loading {
				SkeletonRow()
			}
			if let snapshot = state.snapshot {
				ForEach(Array(snapshot.metrics.filter { $0.group == .limit }.enumerated()), id: \.element.id) { index, metric in
					if index > 0 {
						Spacer().frame(height: 14)
					}
					MetricRow(metric: metric, now: now)
				}

				let products = snapshot.metrics.filter { $0.group == .product }
				if !products.isEmpty {
					Spacer().frame(height: 22)
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

			// The skeleton already says a reading is on its way, so the line that
			// would otherwise say "Loading" is left out while it is showing.
			if !loading {
				Spacer().frame(height: 22)

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
			}

			if !state.signInLink.isEmpty {
				SignInLink(address: state.signInLink).padding(.top, 12)
			}
		}
	}
}

/// The shape a usage row will take, while the first reading is on its way.
///
/// One row, not one per reading the provider turns out to have: how many it
/// reports is not known until it answers, and a column of rows that collapses
/// to a different number is a worse thing to look at than a single row that
/// fills in.
private struct SkeletonRow: View {
	var body: some View {
		HStack(spacing: 10) {
			SkeletonBlock(width: 138)
			UsageBar(percent: nil)
			SkeletonBlock(width: 28)
				.frame(width: 42, alignment: .trailing)
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
	var body: some View {
		if let url = URL(string: address) {
			Text(instruction(url: url))
				.font(.system(size: 11))
				.foregroundStyle(.secondary)
				.fixedSize(horizontal: false, vertical: true)
		}
	}

	/// Keep the full authorization URL in the link destination, never in its label.
	private func instruction(url: URL) -> AttributedString {
		var text = AttributedString("If the browser doesn’t open, ")
		var link = AttributedString("click here")
		link.link = url
		text += link
		text += AttributedString(".")
		return text
	}
}
