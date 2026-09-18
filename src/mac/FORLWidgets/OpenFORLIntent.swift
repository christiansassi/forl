//
//  OpenFORLIntent.swift
//  What a click on the Control Center control does.
//
//  Opens the app, which is where the panel, the settings and the sign-in are.
//  The control itself shows one number and offers no choice, because Control
//  Center has room for one number and no choice.
//

import AppIntents
import Foundation

/// Bring the app forward.
struct OpenFORLIntent: AppIntent {
	static let title: LocalizedStringResource = "Open FORL"
	static let openAppWhenRun = true

	/// Run the intent.
	///
	/// - Returns: An empty result, the app having been opened by the system on
	///   the strength of `openAppWhenRun`.
	/// - Throws: Nothing.
	func perform() async throws -> some IntentResult {
		.result()
	}
}
