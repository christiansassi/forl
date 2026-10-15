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

			if let state = store.state(for: selectedProviderKey), let snapshot = state.snapshot {
				let key = state.provider.key
				Spacer().frame(height: 22)
				Text("Panel")
					.font(.system(size: 11, weight: .semibold))
					.foregroundStyle(.secondary)
					.padding(.bottom, 10)
				MetricChecklist(
					snapshot: snapshot,
					accent: state.provider.accent,
					chosen: store.preferences.panelShown(for: key),
					onToggle: { store.preferences.togglePanel($0, for: key) }
				)

				Spacer().frame(height: 22)
				Text("Show")
					.font(.system(size: 11, weight: .semibold))
					.foregroundStyle(.secondary)
					.padding(.bottom, 10)
				MetricChecklist(
					snapshot: snapshot,
					accent: state.provider.accent,
					chosen: store.preferences.selected(for: key),
					onToggle: {
						store.preferences.toggle($0, for: key)
						store.publish()
					}
				)
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

/// One checkbox per usage a reading reports, ticked for the ones chosen.
///
/// The Panel section, which picks the rows the panel shows, and the Show
/// section, which picks the menu bar items, are both this list.
private struct MetricChecklist: View {
	/// The reading that names the usages there are.
	var snapshot: UsageSnapshot
	/// The color of a ticked box.
	var accent: Color
	/// Keys of the usages ticked.
	var chosen: [String]
	/// Called with a usage's key when its box is clicked.
	var onToggle: (String) -> Void

	var body: some View {
		VStack(alignment: .leading, spacing: 0) {
			ForEach(snapshot.metrics) { metric in
				Toggle(metric.label, isOn: Binding(
					get: { chosen.contains(metric.key) },
					set: { _ in onToggle(metric.key) }
				))
				.toggleStyle(.checkbox)
				.tint(accent)
				.font(.system(size: 12))
				.frame(minHeight: 20, alignment: .leading)
				.padding(.vertical, 1)
			}
		}
	}
}
