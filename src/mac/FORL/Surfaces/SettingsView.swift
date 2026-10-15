//
//  SettingsView.swift
//  The second page of the panel.
//
//  Three groups: where the readings are shown, which usages each service shows,
//  and who is signed in to each. A service with no sign-in shows only the word
//  that starts one, because everything else about it is a choice about readings
//  that are not arriving.
//

import ServiceManagement
import SwiftUI
import os

private let log = Logger(subsystem: "io.forl.app", category: "settings")

/// The chevron that leaves the settings.
private struct BackButton: View {
	/// The color the chevron takes while the pointer is over it.
	var accent: Color
	/// Called when the chevron is clicked.
	var action: () -> Void
	/// Whether the pointer is over the chevron.
	@State private var hovering = false

	var body: some View {
		Button(action: action) {
			Image(systemName: "chevron.backward")
				.font(.system(size: 12))
				.frame(width: 16, height: 28, alignment: .leading)
				.contentShape(Rectangle())
		}
		.buttonStyle(.plain)
		.foregroundStyle(hovering ? AnyShapeStyle(accent) : AnyShapeStyle(.secondary))
		.onHover { hovering = $0 }
		.help("Back")
		.accessibilityLabel("Back to usage")
	}
}

/// The settings page.
struct SettingsView: View {
	/// Everything the app is showing.
	@Bindable var store: UsageStore
	@Binding var selectedProviderKey: String
	/// Called when the user leaves the settings.
	var onBack: () -> Void

	var body: some View {
		VStack(alignment: .leading, spacing: 0) {
			HStack(spacing: 8) {
				BackButton(accent: store.state(for: selectedProviderKey)?.provider.accent ?? .accentColor, action: onBack)
				Text("Settings")
					.font(.system(size: 13, weight: .semibold))
				Spacer()
			}
			.padding(.bottom, 16)

			if let state = store.state(for: selectedProviderKey) {
				Text("Account")
					.font(.system(size: 11, weight: .semibold))
					.foregroundStyle(.secondary)
					.padding(.bottom, 8)
				AccountRow(state: state, store: store)
				Spacer().frame(height: 22)
			}

			Text("General")
				.font(.system(size: 11, weight: .semibold))
				.foregroundStyle(.secondary)
				.padding(.bottom, 8)

			HStack {
				Text("Start at login")
				Spacer()
				Toggle("Start at login", isOn: Binding(
					get: { store.preferences.startAtLogin },
					set: { setStartAtLogin($0) }
				))
				.labelsHidden()
				.fixedSize()
				.tint(store.state(for: selectedProviderKey)?.provider.accent ?? .accentColor)
			}

			HStack {
				Text("Show plan")
				Spacer()
				Toggle("Show plan", isOn: Binding(
					get: { store.preferences.showPlan },
					set: { store.preferences.showPlan = $0 }
				))
				.labelsHidden()
				.fixedSize()
				.tint(store.state(for: selectedProviderKey)?.provider.accent ?? .accentColor)
			}
			.padding(.top, 10)

			if let state = store.state(for: selectedProviderKey), let snapshot = state.snapshot {
				Spacer().frame(height: 22)
				ShowTable(state: state, snapshot: snapshot, store: store)
			}
		}
		.toggleStyle(.switch)
	}

	/// Ask the system to start the app at login, or to stop.
	///
	/// - Parameter enabled: What the user set the switch to.
	/// - Returns: Nothing. The switch is put back when the system refuses.
	private func setStartAtLogin(_ enabled: Bool) {
		do {
			if enabled {
				try SMAppService.mainApp.register()
			} else {
				try SMAppService.mainApp.unregister()
			}
			store.preferences.startAtLogin = enabled
		} catch {
			// Nothing was registered, so the switch goes back rather than being
			// left claiming something that is not so.
			log.error("Cannot change the login item: \(error.localizedDescription, privacy: .public)")
			store.preferences.startAtLogin = SMAppService.mainApp.status == .enabled
		}
	}
}

/// One service, and who is signed in to it.
private struct AccountRow: View {
	/// The provider to draw.
	var state: ProviderState
	/// Everything the app is showing, for the selection.
	@Bindable var store: UsageStore

	var body: some View {
		VStack(alignment: .leading, spacing: 0) {
			HStack(spacing: 8) {
				ProviderMark(symbolName: state.provider.symbolName, tint: state.provider.accent, size: 14)
				Text(state.provider.label)
					.font(.system(size: 13))
				Spacer()
				Button(state.signedIn ? "Sign out" : "Sign in") {
					if state.signedIn {
						state.signOut()
						store.publish()
					} else {
						Task {
							await state.signIn()
							store.refresh()
						}
					}
				}
				.buttonStyle(.link)
				.foregroundStyle(state.provider.accent)
				.disabled(state.signingIn)
			}

			Text(state.signedIn ? (state.account.isEmpty ? "Signed in" : state.account) : "Not signed in")
				.font(.system(size: 11))
				.foregroundStyle(.secondary)
				.padding(.top, 2)
			if !state.signInLink.isEmpty {
				SignInControls(state: state).padding(.top, 12)
			}
		}
	}
}

/// Every usage a reading reports, with a checkbox for the panel and one for
/// the menu bar.
///
/// The section heading shares its line with the headings of the two columns,
/// so the table needs no line of its own for them.
private struct ShowTable: View {
	/// The provider to draw.
	var state: ProviderState
	/// The reading that names the usages there are.
	var snapshot: UsageSnapshot
	/// Everything the app is showing, for both selections.
	@Bindable var store: UsageStore

	var body: some View {
		let key = state.provider.key
		// A grid makes each checkbox column as wide as its heading and centers
		// the boxes under it, and its last column ends where the switches above
		// it do, so the headings line up with them.
		Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 4) {
			GridRow {
				Text("Show")
					.frame(maxWidth: .infinity, alignment: .leading)
					.padding(.bottom, 6)
				Text("Panel")
					.gridColumnAlignment(.center)
				Text("Menu bar")
					.gridColumnAlignment(.center)
			}
			.font(.system(size: 11, weight: .semibold))
			.foregroundStyle(.secondary)

			ForEach(snapshot.metrics) { metric in
				GridRow {
					Text(metric.label)
						.font(.system(size: 12))
						.lineLimit(1)
						.frame(minHeight: 20)
					checkbox(metric.label, isOn: store.preferences.panelShown(for: key).contains(metric.key)) {
						store.preferences.togglePanel(metric.key, for: key)
					}
					checkbox(metric.label, isOn: store.preferences.selected(for: key).contains(metric.key)) {
						store.preferences.toggle(metric.key, for: key)
						store.publish()
					}
				}
			}
		}
	}

	/// Return one checkbox, centered under its column's heading.
	///
	/// - Parameters:
	///   - label: What the box is for, read out by accessibility tools.
	///   - isOn: Whether the box is ticked.
	///   - toggle: Called when the box is clicked.
	/// - Returns: The checkbox.
	private func checkbox(_ label: String, isOn: Bool, toggle: @escaping () -> Void) -> some View {
		Toggle(label, isOn: Binding(get: { isOn }, set: { _ in toggle() }))
			.toggleStyle(.checkbox)
			.labelsHidden()
			.tint(state.provider.accent)
	}
}
