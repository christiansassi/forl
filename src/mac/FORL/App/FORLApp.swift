//
//  FORLApp.swift
//  Where the app starts.
//
//  There is no main window. The app is an accessory until the Dock surface says
//  otherwise, its interface is the menu bar items and the panel they open, and
//  its readings reach the widgets through the group container rather than
//  through any window at all.
//

import AppKit
import SwiftUI

/// The application.
@main
struct FORLApp: App {
	@NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

	var body: some Scene {
		// No scene of its own: every surface this app has is built by the
		// delegate, because a menu bar item and a Dock icon are not windows and
		// SwiftUI has nothing to open for them.
		Settings {
			EmptyView()
		}
	}
}

/// Builds every surface and keeps them in step with the readings.
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
	private var store: UsageStore!
	private var menuBar: MenuBarController!
	private var panel: PanelController!
	private var observation: NSObjectProtocol?
	private var redraw: Task<Void, Never>?

	/// Build the surfaces and start polling.
	///
	/// - Parameter notification: The launch notification, which this ignores.
	/// - Returns: Nothing.
	func applicationDidFinishLaunching(_ notification: Notification) {
		let preferences = Preferences()
		store = UsageStore(preferences: preferences)
		panel = PanelController(store: store)
		menuBar = MenuBarController(store: store) { [weak self] button in
			self?.panel.toggle(under: button)
		}

		applySurfaces()
		store.start()
		startRedrawing()
		signInIfNeeded()
	}

	/// Open the panel when the user clicks the Dock icon.
	///
	/// - Parameters:
	///   - sender: The application, which this ignores.
	///   - flag: Whether any window is already showing, which this ignores.
	/// - Returns: False, so Cocoa does not go looking for a window to bring
	///   forward on top of what this already did.
	func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
		panel.show(under: menuBar.firstButton())
		return false
	}

	/// Stop polling before the process goes.
	///
	/// - Parameter notification: The termination notification, ignored.
	/// - Returns: Nothing.
	func applicationWillTerminate(_ notification: Notification) {
		redraw?.cancel()
		store.stop()
		menuBar.clear()
	}

	/// Redraw the surfaces whenever anything they show has changed.
	///
	/// Polled on a short timer rather than observed field by field, because the
	/// surfaces are cheap to rebuild and the alternative is an observation on
	/// every value of every provider.
	///
	/// - Returns: Nothing.
	private func startRedrawing() {
		redraw = Task { [weak self] in
			while !Task.isCancelled {
				self?.applySurfaces()
				try? await Task.sleep(for: .milliseconds(500))
			}
		}
	}

	/// Show or hide each surface according to the stored preferences.
	///
	/// - Returns: Nothing.
	private func applySurfaces() {
		menuBar.sync()

		guard store.preferences.dock else {
			NSApp.setActivationPolicy(.accessory)
			return
		}
		NSApp.setActivationPolicy(.regular)

		guard
			let state = store.active.first,
			let metric = state.displayed(store.preferences).first
		else {
			DockIcon.show(percent: nil, accent: .accentColor, name: "FORL")
			return
		}
		DockIcon.show(
			percent: metric.percent,
			accent: state.provider.accent,
			name: state.tooltip(for: metric)
		)
	}

	/// Put the user in front of a sign-in when nobody is signed in at all.
	///
	/// - Returns: Nothing.
	private func signInIfNeeded() {
		guard store.active.isEmpty else {
			return
		}
		panel.show(under: menuBar.firstButton())
	}
}
