//
//  Provider.swift
//  The services the app can report on.
//
//  A provider is everything that differs between Claude and ChatGPT: how the
//  sign-in is obtained, which endpoint reports usage, how that response is
//  shaped, and how the product is named and colored. Everything after the
//  provider, the dials, the panel and the polling, is shared.
//

import Foundation
import SwiftUI

/// One service the app can report on.
protocol Provider: Sendable {
	/// How this service is named and colored, which is all a surface needs and
	/// all the widget extension is given.
	var identity: ProviderIdentity { get }
	/// What this service's browser sign-in needs.
	var oauth: OAuthClient { get }

	/// Run the browser sign-in and store the result.
	///
	/// Takes as long as the user does, so it belongs off the thread drawing the
	/// interface.
	///
	/// - Parameter onAddress: Called once with the address to sign in at and
	///   whether a browser was opened at it.
	/// - Returns: Who is now signed in, as the settings should name them.
	/// - Throws: `UsageError` when the sign-in was refused or not completed.
	func signIn(onAddress: @Sendable @escaping (String, Bool) -> Void) async throws -> String

	/// Take one usage reading.
	///
	/// - Returns: The current reading.
	/// - Throws: `UsageError` when the sign-in cannot be used or the endpoint
	///   cannot be reached.
	func read() async throws -> UsageSnapshot

	/// Send one short message, which starts the five hour session if none is
	/// running.
	///
	/// - Returns: Nothing, once the service has accepted the message.
	/// - Throws: `UsageError` when the sign-in cannot be used or the endpoint
	///   cannot be reached.
	func startSession() async throws
}

extension Provider {
	/// Stable identifier used in storage and in window names.
	var key: String { identity.key }
	/// Product name shown in the panel title.
	var label: String { identity.label }
	/// Name of the mark inside the asset catalog.
	var symbolName: String { identity.symbolName }
	/// Brand color, used for the mark and the dial but never for a value.
	var accent: Color { identity.accent }

	/// Return who is signed in to this provider, and whether anyone is.
	///
	/// - Returns: The account as the settings should name them, empty when the
	///   sign-in reported no name, and whether there is a sign-in at all.
	func account() -> (name: String, signedIn: Bool) {
		guard let tokens = TokenStore.load(key) else {
			return ("", false)
		}
		return (tokens.account, true)
	}

	/// Forget this provider's sign-in.
	///
	/// - Returns: Nothing.
	func signOut() {
		TokenStore.clear(key)
	}
}

/// Every provider the app knows, in the order the interface shows them.
let allProviders: [any Provider] = [ClaudeProvider(), CodexProvider()]

/// Return the provider with a given key.
///
/// - Parameter key: One of the provider keys, such as "claude".
/// - Returns: The matching provider, or nil when no provider has that key.
func provider(for key: String) -> (any Provider)? {
	allProviders.first { $0.key == key }
}

/// Return one named object of a response, or an empty one.
///
/// - Parameters:
///   - document: The decoded response.
///   - name: Name of the object to take, such as "account".
/// - Returns: The object, empty when it is missing or is not an object.
func section(_ document: [String: Any], _ name: String) -> [String: Any] {
	document[name] as? [String: Any] ?? [:]
}

/// Return an ISO 8601 timestamp from a provider as a moment.
///
/// - Parameter value: Timestamp text such as "2026-09-16T12:00:00+00:00".
/// - Returns: The parsed moment, or nil when it is missing or unparsable.
func parseTimestamp(_ value: Any?) -> Date? {
	guard let text = value as? String, !text.isEmpty else {
		return nil
	}
	let withFraction = ISO8601DateFormatter()
	withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
	return withFraction.date(from: text) ?? ISO8601DateFormatter().date(from: text)
}

/// Return a Unix timestamp from a provider as a moment.
///
/// - Parameter value: Seconds since the epoch.
/// - Returns: The parsed moment, or nil when it is missing or unusable.
func parseEpoch(_ value: Any?) -> Date? {
	guard let seconds = value as? Double, seconds > 0 else {
		return nil
	}
	return Date(timeIntervalSince1970: seconds)
}
