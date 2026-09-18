//
//  ProviderState.swift
//  What the app knows about one service.
//
//  One of these per provider: the last reading, whether one is in flight, what
//  to say about the sign-in, and the sign-in itself. Nothing here draws. The
//  surfaces read it and the store drives it, which is what lets the menu bar,
//  the Dock, the panel and the widget all show the same thing without any of
//  them asking an endpoint.
//

import Foundation
import Observation

/// The state of one provider, as every surface reads it.
@MainActor
@Observable
final class ProviderState: Identifiable {
	/// The service this is the state of.
	let provider: any Provider

	/// The last reading that arrived, or nil before the first one and after a
	/// sign-out.
	private(set) var snapshot: UsageSnapshot?
	/// What to say about the sign-in, empty when there is nothing to say.
	private(set) var signInMessage = ""
	/// The address a sign-in under way is waiting at, empty when none is.
	private(set) var signInLink = ""
	/// Whether a reading is in flight.
	private(set) var refreshing = false
	/// Whether a sign-in is under way.
	private(set) var signingIn = false
	/// Who is signed in, empty when the sign-in reported no name.
	private(set) var account = ""
	/// Whether there is a sign-in at all.
	private(set) var signedIn = false

	/// Set when the user signs out, which is the one case where being signed out
	/// must not put a browser window in front of them.
	private var signedOut = false
	/// Whether a sign-in has already been offered for this spell of being
	/// signed out, so one left undone does not raise a browser window a minute.
	private var prompted = false

	var id: String { provider.key }

	/// Build the state of one provider and read who is signed in to it.
	///
	/// - Parameter provider: The service this is the state of.
	/// - Returns: Nothing.
	init(provider: any Provider) {
		self.provider = provider
		refreshAccount()
	}

	/// Return the metrics the user chose that this reading still reports.
	///
	/// A scoped limit disappears once its window empties, and a product only
	/// appears once it has been used, so the selection is filtered against what
	/// the reading actually carries.
	///
	/// - Parameter preferences: Where the selection is stored.
	/// - Returns: The metrics to draw a surface for, in selection order, and the
	///   session window when nothing else survives.
	func displayed(_ preferences: Preferences) -> [Metric] {
		guard let snapshot else {
			return []
		}
		let available = snapshot.metrics
		let chosen = preferences.selected(for: provider.key)
		let kept = chosen.compactMap { key in available.first { $0.key == key } }
		return kept.isEmpty ? [available[0]] : kept
	}

	/// Return the hover text for one metric.
	///
	/// Hovering is a question about the limit, not about the app, so a failed
	/// attempt does not change the answer. The exception is a sign-in that has
	/// run out, which takes the text because until it is fixed there is no
	/// answer to give.
	///
	/// - Parameter metric: The metric the surface shows.
	/// - Returns: Text such as "34% - Current session".
	func tooltip(for metric: Metric) -> String {
		signInMessage.isEmpty
			? Formatting.tooltip(value: metric.percent, label: metric.label)
			: signInMessage
	}

	/// Return how long is left before the next reading is taken.
	///
	/// - Parameter interval: The delay between readings.
	/// - Returns: Seconds remaining, 0 once the reading is due and 0 when there
	///   has never been one.
	func secondsToNextUpdate(interval: TimeInterval) -> TimeInterval {
		guard let snapshot else {
			return 0
		}
		return max(0, interval - Date().timeIntervalSince(snapshot.fetchedAt))
	}

	/// Return the line describing how fresh the reading is.
	///
	/// A failure the user can do something about, which means signing in again,
	/// is the one thing worth saying and it takes the line. A failure they
	/// cannot, such as a busy endpoint, is not reported at all: the reading on
	/// screen is still the last good one and its age says the rest.
	///
	/// - Parameter interval: The delay between readings.
	/// - Returns: The sign-in instruction when there is one, otherwise the
	///   countdown, or "Loading" before the first reading.
	func statusText(interval: TimeInterval) -> String {
		if !signInMessage.isEmpty {
			return signInMessage
		}
		guard snapshot != nil else {
			return signedIn ? "Loading" : "Not signed in"
		}
		return Formatting.nextUpdate(in: secondsToNextUpdate(interval: interval))
	}

	/// Take one reading, and keep whichever outcome is worth keeping.
	///
	/// A failed attempt keeps the previous snapshot in place. Only one the user
	/// can fix, by signing in again, is reported; a brief network problem
	/// neither blanks the surfaces nor puts a message in front of them.
	///
	/// - Returns: Nothing. Does nothing when nobody is signed in.
	func poll() async {
		guard signedIn, !signingIn else {
			return
		}
		refreshing = true
		defer { refreshing = false }
		do {
			snapshot = try await provider.read()
			if !signedOut {
				signInMessage = ""
				prompted = false
			}
		} catch let error as UsageError {
			guard error.needsSignIn else {
				return
			}
			if !signingIn, !signedOut {
				signInMessage = error.errorDescription ?? OAuth.expiredMessage
			}
			promptSignInIfNeeded()
		} catch {
			return
		}
	}

	/// Sign in through the browser.
	///
	/// - Returns: Nothing. Does nothing while a sign-in is already under way.
	func signIn() async {
		guard !signingIn else {
			return
		}
		signingIn = true
		signedOut = false
		signInMessage = "Signing in. Finish in the browser."

		defer {
			signingIn = false
			signInLink = ""
			refreshAccount()
		}

		do {
			_ = try await provider.signIn { [weak self] address, opened in
				Task { @MainActor in
					self?.signInLink = address
					self?.signInMessage = opened
						? "Signing in. Finish in the browser."
						: "No browser opened. Use the address below."
				}
			}
			signInMessage = ""
			// The reading on screen, if there is one, belongs to whoever was
			// signed in before, so it goes rather than stands under the new name.
			snapshot = nil
		} catch let error as UsageError {
			signInMessage = error.errorDescription ?? OAuth.rejectedMessage
		} catch {
			signInMessage = error.localizedDescription
		}
	}

	/// Forget the sign-in, and stop reporting until the user signs in again.
	///
	/// This is also how the app is moved to another subscription on the same
	/// machine: sign out of one and in to the other.
	///
	/// - Returns: Nothing.
	func signOut() {
		provider.signOut()
		signedOut = true
		prompted = false
		snapshot = nil
		signInLink = ""
		signInMessage = "Signed out."
		refreshAccount()
	}

	/// Read who is signed in from the keychain.
	///
	/// - Returns: Nothing.
	func refreshAccount() {
		let stored = provider.account()
		account = stored.name
		signedIn = stored.signedIn
	}

	/// Put the user in front of the sign-in when a reading says one is needed.
	///
	/// Started once for each spell of being signed out rather than at every
	/// reading, and never after the user signed out on purpose.
	///
	/// - Returns: Nothing.
	private func promptSignInIfNeeded() {
		guard !signInMessage.isEmpty, !prompted, !signedOut else {
			return
		}
		prompted = true
		Task { await signIn() }
	}
}
