//
//  UsageStore.swift
//  The running app: every provider, polled on a schedule.
//
//  One of these for the whole app. It holds the state of each service, polls
//  them together, and after every round writes what the widget should show into
//  the group container and asks WidgetKit to reload. Nothing else writes that
//  container, so the widget and the app can never disagree about a reading.
//
//  The old PyObjC widget kept its sign-ins in a file beside its preferences.
//  That file is read once, on a first run, so nobody has to sign in again for
//  the sake of a rewrite, and is then left where it is.
//

import Foundation
import Observation
import WidgetKit
import os

private let log = Logger(subsystem: "io.forl.app", category: "store")

/// Everything the app is currently showing.
@MainActor
@Observable
final class UsageStore {
	/// The state of every provider, in the order the interface shows them.
	private(set) var states: [ProviderState]
	/// What the user has chosen, shared with the widget.
	let preferences: Preferences

	/// The task that polls on a schedule, cancelled when the app quits.
	private var loop: Task<Void, Never>?

	/// Build the store and read who is signed in to each provider.
	///
	/// - Parameter preferences: What the user has chosen.
	/// - Returns: Nothing.
	init(preferences: Preferences) {
		self.preferences = preferences
		states = allProviders.map(ProviderState.init(provider:))
		LegacyImport.runIfNeeded()
		states.forEach { $0.refreshAccount() }
	}

	/// Return the state of one provider.
	///
	/// - Parameter key: Key of the provider, such as "claude".
	/// - Returns: The state, or nil when no provider has that key.
	func state(for key: String) -> ProviderState? {
		states.first { $0.provider.key == key }
	}

	/// Return the providers with a sign-in stored, in interface order.
	///
	/// - Returns: The states worth showing, which is what the surfaces draw.
	var active: [ProviderState] {
		states.filter(\.signedIn)
	}

	/// Start polling, and keep polling until the app quits.
	///
	/// - Returns: Nothing.
	func start() {
		guard loop == nil else {
			return
		}
		loop = Task { [weak self] in
			while !Task.isCancelled {
				await self?.pollAll()
				try? await Task.sleep(for: .seconds(pollInterval))
			}
		}
	}

	/// Stop polling.
	///
	/// - Returns: Nothing.
	func stop() {
		loop?.cancel()
		loop = nil
	}

	/// Take one reading from every signed-in provider, at the same time.
	///
	/// - Returns: Nothing, once every reading has come back or failed.
	func pollAll() async {
		await withTaskGroup(of: Void.self) { group in
			for state in states where state.signedIn {
				group.addTask { @MainActor in
					await state.poll()
				}
			}
		}
		publish()
	}

	/// Take one reading now rather than waiting out the interval.
	///
	/// - Returns: Nothing.
	func refresh() {
		Task { await pollAll() }
	}

	/// Write what the widget should show, and ask WidgetKit to redraw it.
	///
	/// - Returns: Nothing.
	func publish() {
		let state = SharedState(readings: states.filter(\.signedIn).map { provider in
			StoredReading(
				providerKey: provider.provider.key,
				snapshot: provider.snapshot,
				signInMessage: provider.signInMessage
			)
		})
		SharedStore.save(state)
		WidgetCenter.shared.reloadAllTimelines()
	}
}

/// The one-off read of what the PyObjC widget left behind.
enum LegacyImport {
	/// The file that widget kept its sign-ins in.
	private static var credentialsURL: URL? {
		FileManager.default
			.urls(for: .applicationSupportDirectory, in: .userDomainMask)
			.first?
			.appendingPathComponent("forl/credentials.json")
	}

	/// The flag that says this has already been done.
	private static let doneKey = "importedLegacyCredentials"

	/// Move the sign-ins of the widget this app replaces into the keychain.
	///
	/// Run once. A provider that already has a sign-in in the keychain is left
	/// alone, so this can never undo a sign-in made here.
	///
	/// - Returns: Nothing. Anything that cannot be read is skipped: the cost is
	///   one trip through the browser, not a launch.
	static func runIfNeeded() {
		guard !UserDefaults.shared.bool(forKey: doneKey) else {
			return
		}

		guard
			let url = credentialsURL,
			let data = try? Data(contentsOf: url),
			let decoded = try? JSONSerialization.jsonObject(with: data),
			let document = decoded as? [String: [String: Any]]
		else {
			// Nothing readable there. The flag stays clear, so a file that turns
			// up later, or one this build could not reach, is still picked up
			// the next time rather than written off forever.
			return
		}
		UserDefaults.shared.set(true, forKey: doneKey)

		for provider in allProviders where TokenStore.load(provider.key) == nil {
			guard
				let section = document[provider.key],
				let access = section["access_token"] as? String,
				!access.isEmpty
			else {
				continue
			}
			let expires = section["expires_at"] as? Double ?? 0
			let tokens = Tokens(
				accessToken: access,
				refreshToken: section["refresh_token"] as? String ?? "",
				expiresAt: expires > 0 ? Date(timeIntervalSince1970: expires) : nil,
				account: section["account"] as? String ?? "",
				plan: section["plan"] as? String ?? "",
				extra: section["extra"] as? [String: String] ?? [:]
			)
			do {
				try TokenStore.save(provider.key, tokens)
				log.info("Imported the stored sign-in for \(provider.key, privacy: .public)")
			} catch {
				log.error("Could not import \(provider.key, privacy: .public)")
			}
		}
	}
}
