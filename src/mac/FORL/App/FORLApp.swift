//
//  FORLApp.swift
//  Where the app starts.
//
//  There is no main window. The app is an accessory with menu bar items and a panel,
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
		// delegate, because menu bar items are not windows and
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
		NSApp.setActivationPolicy(.accessory)
		stopDockHelpers()
		LegacyImport.migrateGroupIfNeeded()
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

	/// Open the panel when the user launches the app again.
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

	/// Open the panel on the provider requested by a widget or control.
	func application(_ application: NSApplication, open urls: [URL]) {
		guard let key = urls.first?.pathComponents.last,
			providerIdentity(for: key) != nil else { return }
		NotificationCenter.default.post(name: .forlSelectProvider, object: key)
		panel.show(under: menuBar.firstButton())
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
	}

	/// Stop helper processes left running by versions that offered Dock tiles.
	private func stopDockHelpers() {
		for bundleID in ["io.forl.app.dock.claude", "io.forl.app.dock.chatgpt"] {
			NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).forEach { $0.terminate() }
		}
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
