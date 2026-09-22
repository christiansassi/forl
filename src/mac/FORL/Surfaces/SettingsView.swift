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

			// Beside the login switch rather than under the account: both are about
			// what the app does on its own. It belongs to the service of the tab,
			// and only one that is signed in has a session to start.
			if let state = store.state(for: selectedProviderKey), state.signedIn {
				SessionStartSection(state: state, store: store)
					.padding(.top, 10)
			}

			if let state = store.state(for: selectedProviderKey) {
				Spacer().frame(height: 22)
				Text("Account")
					.font(.system(size: 11, weight: .semibold))
					.foregroundStyle(.secondary)
					.padding(.bottom, 8)
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
				.foregroundStyle(state.provider.accent)
				.disabled(state.signingIn)
			}

			Text(state.signedIn ? (state.account.isEmpty ? "Signed in" : state.account) : "Not signed in")
				.font(.system(size: 11))
				.foregroundStyle(.secondary)
				.padding(.top, 2)

			if let snapshot = state.snapshot {
				Spacer().frame(height: 22)
				Text("Show")
					.font(.system(size: 11, weight: .semibold))
					.foregroundStyle(.secondary)
					.padding(.bottom, 10)

				ForEach(snapshot.metrics) { metric in
					Toggle(metric.label, isOn: Binding(
						get: { store.preferences.selected(for: state.provider.key).contains(metric.key) },
						set: { _ in
							store.preferences.toggle(metric.key, for: state.provider.key)
							store.publish()
						}
					))
					.toggleStyle(.checkbox)
					.tint(state.provider.accent)
					.font(.system(size: 12))
					.frame(minHeight: 20, alignment: .leading)
					.padding(.vertical, 1)
				}
			}
		}
	}
}

/// When the service's session is started on the user's behalf.
///
/// The same setting the Windows widget has: a switch, and while it is on, the
/// days of the week, the time of day and how late the message may still go out.
private struct SessionStartSection: View {
	/// The provider the schedule belongs to.
	var state: ProviderState
	/// Everything the app is showing, for the stored schedule.
	@Bindable var store: UsageStore

	var body: some View {
		let key = state.provider.key
		let accent = state.provider.accent
		let schedule = store.preferences.sessionStart(for: key)
		VStack(alignment: .leading, spacing: 0) {
			HStack {
				Text("Start usage window automatically")
				Spacer()
				Toggle("Start usage window automatically", isOn: Binding(
					get: { schedule.enabled },
					set: { store.preferences.setSessionStart(schedule.switched($0, now: Date()), for: key) }
				))
				.labelsHidden()
				.fixedSize()
				.tint(accent)
			}

			if schedule.enabled {
				HStack(spacing: 0) {
					ForEach(Array(zip(SessionStart.allWeekdays, weekdayInitials)), id: \.0) { weekday, initial in
						if weekday > 1 {
							Spacer(minLength: 0)
						}
						WeekdayButton(initial: initial, chosen: schedule.weekdays.contains(weekday), accent: accent) {
							store.preferences.setSessionStart(schedule.toggledWeekday(weekday), for: key)
						}
					}
				}
				.padding(.top, 10)

				HStack(spacing: 2) {
					Text("Time")
					Spacer()
					// Laid out from the right hand edge, so the minutes end where
					// every other control in the settings does.
					StepButton(sign: "−", accent: accent) { step(schedule, hours: -1, minutes: 0) }
					Text(schedule.clock().hour).monospacedDigit()
					StepButton(sign: "+", accent: accent) { step(schedule, hours: 1, minutes: 0) }
					Text(":").padding(.horizontal, 4)
					StepButton(sign: "−", accent: accent) { step(schedule, hours: 0, minutes: -SessionStart.minuteStep) }
					Text(schedule.clock().minute).monospacedDigit()
					StepButton(sign: "+", accent: accent) { step(schedule, hours: 0, minutes: SessionStart.minuteStep) }
				}
				.padding(.top, 10)

				HStack {
					Text("Late by up to")
					Spacer()
					Text("\(schedule.graceMinutes) min")
						.monospacedDigit()
						.foregroundStyle(.secondary)
				}
				.padding(.top, 10)

				Slider(
					value: Binding(
						get: { Double(schedule.graceMinutes) },
						set: { store.preferences.setSessionStart(schedule.withGrace(Int($0.rounded())), for: key) }
					),
					in: 0...Double(SessionStart.maxGraceMinutes),
					step: Double(SessionStart.minuteStep)
				)
				.controlSize(.small)
				.tint(accent)
				.padding(.top, 6)
			}
		}
	}

	/// The days of the week by their initials, Monday first, in ISO order.
	private let weekdayInitials = ["M", "T", "W", "T", "F", "S", "S"]

	/// Move the time and keep the result.
	///
	/// - Parameters:
	///   - schedule: The schedule as it stands.
	///   - hours: Hours to add, negative to go back.
	///   - minutes: Minutes to add, negative to go back.
	/// - Returns: Nothing.
	private func step(_ schedule: SessionStart, hours: Int, minutes: Int) {
		store.preferences.setSessionStart(
			schedule.steppedTime(hours: hours, minutes: minutes, now: Date()),
			for: state.provider.key
		)
	}
}

/// One day of the week the session may be started on.
///
/// A chosen day is filled with the color of the service; a day that is not is
/// an outline, which takes that color, ring and initial, under the pointer, as
/// the other controls of the settings do.
private struct WeekdayButton: View {
	/// The day's initial.
	var initial: String
	/// Whether the session is started on this day.
	var chosen: Bool
	/// The color of the service.
	var accent: Color
	/// Called when the day is clicked.
	var action: () -> Void
	/// Whether the pointer is over the day.
	@State private var hovering = false

	var body: some View {
		Button(action: action) {
			Text(initial)
				.font(.system(size: 11, weight: .semibold))
				// The window's own color reads on a filled circle whichever the
				// service's color is: white on its orange, and the opposite of the
				// label color on a service drawn in the label color.
				.foregroundStyle(chosen ? AnyShapeStyle(Color(nsColor: .windowBackgroundColor)) : hovering ? AnyShapeStyle(accent) : AnyShapeStyle(.secondary))
				.frame(width: 28, height: 28)
				.background {
					Circle()
						.fill(chosen ? AnyShapeStyle(accent) : AnyShapeStyle(.clear))
						.overlay {
							Circle()
								.stroke(chosen || hovering ? AnyShapeStyle(accent) : AnyShapeStyle(.tertiary), lineWidth: 1)
						}
				}
				.contentShape(Circle())
		}
		.buttonStyle(.plain)
		.onHover { hovering = $0 }
	}
}

/// One step of the time, a sign that moves a field up or down.
///
/// In the secondary label color, as the gear and the chevron are, and in the
/// color of the service while the pointer is over it.
private struct StepButton: View {
	/// The sign drawn, "−" or "+".
	var sign: String
	/// The color the sign takes while the pointer is over it.
	var accent: Color
	/// Called when the sign is clicked.
	var action: () -> Void
	/// Whether the pointer is over the sign.
	@State private var hovering = false

	var body: some View {
		Button(action: action) {
			Text(sign)
				.font(.system(size: 13, weight: .medium))
				.frame(width: 18, height: 22)
				.contentShape(Rectangle())
		}
		.buttonStyle(.plain)
		.foregroundStyle(hovering ? AnyShapeStyle(accent) : AnyShapeStyle(.secondary))
		.onHover { hovering = $0 }
	}
}
