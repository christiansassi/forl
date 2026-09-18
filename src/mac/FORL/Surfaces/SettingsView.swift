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

/// The settings page.
struct SettingsView: View {
	/// Everything the app is showing.
	@Bindable var store: UsageStore
	/// Called when the user leaves the settings.
	var onBack: () -> Void

	var body: some View {
		VStack(alignment: .leading, spacing: 0) {
			HStack(spacing: 8) {
				Button(action: onBack) {
					Image(systemName: "chevron.backward")
				}
				.buttonStyle(.plain)
				.help("Back")
				Text("Settings")
					.font(.system(size: 13, weight: .semibold))
				Spacer()
			}
			.padding(.bottom, 16)

			Text("Show in")
				.font(.system(size: 11, weight: .semibold))
				.foregroundStyle(.secondary)
				.padding(.bottom, 8)

			Toggle("Menu bar", isOn: Binding(
				get: { store.preferences.menuBar },
				set: { store.preferences.menuBar = $0 }
			))
			.padding(.bottom, 10)

			Toggle("Dock", isOn: Binding(
				get: { store.preferences.dock },
				set: { store.preferences.dock = $0 }
			))
			.padding(.bottom, 10)

			HStack {
				Text("Menu bar style")
				Spacer()
				Picker("", selection: Binding(
					get: { store.preferences.menuBarStyle },
					set: { store.preferences.menuBarStyle = $0 }
				)) {
					ForEach(MenuBarStyle.allCases, id: \.self) { style in
						Text(style.label).tag(style)
					}
				}
				.labelsHidden()
				.pickerStyle(.segmented)
				.fixedSize()
			}

			Text("Widgets are added from the desktop: right click the desktop, choose Edit Widgets, and look for FORL.")
				.font(.system(size: 11))
				.foregroundStyle(.secondary)
				.fixedSize(horizontal: false, vertical: true)
				.padding(.top, 10)

			Divider().opacity(Theme.hairlineOpacity * 8).padding(.vertical, 14)

			Toggle("Start at login", isOn: Binding(
				get: { store.preferences.startAtLogin },
				set: { setStartAtLogin($0) }
			))

			ForEach(store.states) { state in
				Divider().opacity(Theme.hairlineOpacity * 8).padding(.vertical, 14)
				AccountRow(state: state, store: store)
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

/// One service: who is signed in, and which of its usages are shown.
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
				.disabled(state.signingIn)
			}

			Text(state.signedIn ? (state.account.isEmpty ? "Signed in" : state.account) : "Not signed in")
				.font(.system(size: 11))
				.foregroundStyle(.secondary)
				.padding(.top, 2)

			if let snapshot = state.snapshot {
				Text("Show")
					.font(.system(size: 11, weight: .semibold))
					.foregroundStyle(.secondary)
					.padding(.top, 12)
					.padding(.bottom, 6)

				ForEach(snapshot.metrics) { metric in
					Toggle(metric.label, isOn: Binding(
						get: { store.preferences.selected(for: state.provider.key).contains(metric.key) },
						set: { _ in
							store.preferences.toggle(metric.key, for: state.provider.key)
							store.publish()
						}
					))
					.toggleStyle(.checkbox)
					.font(.system(size: 12))
				}
			}
		}
	}
}
