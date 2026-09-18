//
//  UsageError.swift
//  The failures the widget expects and reports rather than crashes on.
//
//  Both providers fail in the same two ways, a sign-in that cannot be used and
//  a request that does not come back, so both throw the cases defined here.
//

import Foundation

/// A failure the widget expects and has something to say about.
enum UsageError: LocalizedError, Sendable {
	/// The stored sign-in is missing, cannot be read, or has run out.
	case credentials(String)
	/// A request could not be made or did not come back.
	case request(String)
	/// An endpoint rejected the token, so a new sign-in is needed.
	case authentication(String)

	/// Return what to put in front of the user.
	///
	/// - Returns: The message the failure was raised with.
	var errorDescription: String? {
		switch self {
		case .credentials(let message), .request(let message), .authentication(let message):
			return message
		}
	}

	/// Return whether signing in again is what fixes this failure.
	///
	/// - Returns: True for a failure the user can act on, false for one that
	///   only waiting or retrying can fix.
	var needsSignIn: Bool {
		switch self {
		case .credentials, .authentication:
			return true
		case .request:
			return false
		}
	}
}
