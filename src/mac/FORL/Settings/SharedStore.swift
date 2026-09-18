//
//  SharedStore.swift
//  The container the app and the widget both read.
//
//  A widget extension is its own sandboxed process and can see nothing of the
//  app that embeds it, so the two share an App Group container. The app writes
//  the latest reading into it after every poll and asks WidgetKit to reload;
//  the widget reads it and makes no request of its own, which is what keeps
//  every token inside the app.
//
//  Only readings and preferences go in here. The sign-ins live in the keychain,
//  because a file in a group container is readable by anything that can reach
//  the container and a refresh token is the sign-in itself.
//

import Foundation
import os

/// The App Group both bundles declare, which is also the name of the directory
/// the container is kept in.
///
/// The prefix is a placeholder rather than a real Apple team identifier. macOS
/// itself does not care what an App Group is called: an ad-hoc signed app is
/// given whatever container it asks for, which is what lets this app share one
/// without an Apple developer account at all. Xcode does care, and refuses to
/// build a macOS target whose group is not prefixed the way a team identifier
/// would be, so it is given something of that shape and nothing of anyone's.
///
/// Signing with a real team later means putting that team's identifier here, and
/// signing in once more, because the container is named after it.
let appGroupIdentifier = "FORLWIDGET.io.forl"

/// The file inside the container that holds the last reading of every provider.
private let readingsFile = "readings.json"

private let log = Logger(subsystem: "io.forl.app", category: "shared")

/// One provider's last reading, as the widget reads it.
struct StoredReading: Codable, Sendable, Equatable {
	/// Key of the provider the reading belongs to.
	var providerKey: String
	/// The reading itself, or nil when the provider is signed in but has not
	/// answered yet.
	var snapshot: UsageSnapshot?
	/// What to say about the sign-in, empty when there is nothing to say.
	var signInMessage: String = ""
}

/// Everything the app puts in front of the widget.
struct SharedState: Codable, Sendable, Equatable {
	/// One entry per provider the user has signed in to, in provider order.
	var readings: [StoredReading] = []
	/// When the app last wrote this.
	var writtenAt: Date = .distantPast

	/// Return the reading of one provider.
	///
	/// - Parameter providerKey: Key of the provider, such as "claude".
	/// - Returns: The stored reading, or nil when that provider has none.
	func reading(for providerKey: String) -> StoredReading? {
		readings.first { $0.providerKey == providerKey }
	}
}

/// Reads and writes the group container both bundles share.
enum SharedStore {
	/// Return the directory the app and the widget share.
	///
	/// - Returns: The group container, or nil when the entitlement is missing,
	///   which is a build that cannot share anything and is worth seeing in the
	///   log rather than silently showing an empty widget.
	static func containerURL() -> URL? {
		guard let url = FileManager.default.containerURL(
			forSecurityApplicationGroupIdentifier: appGroupIdentifier
		) else {
			log.error("No container for app group \(appGroupIdentifier, privacy: .public)")
			return nil
		}
		return url
	}

	/// Return the state the app last wrote.
	///
	/// - Returns: The shared state, empty when nothing has been written yet or
	///   what was written cannot be read.
	static func load() -> SharedState {
		guard
			let url = containerURL()?.appendingPathComponent(readingsFile),
			let data = try? Data(contentsOf: url),
			let state = try? JSONDecoder.shared.decode(SharedState.self, from: data)
		else {
			return SharedState()
		}
		return state
	}

	/// Write the state the widget should show.
	///
	/// - Parameter state: What to put in front of the widget.
	/// - Returns: Nothing. A container that cannot be written costs the widget
	///   its next update and nothing else, so it is logged rather than raised.
	static func save(_ state: SharedState) {
		guard let url = containerURL()?.appendingPathComponent(readingsFile) else {
			return
		}
		var written = state
		written.writtenAt = Date()
		do {
			let data = try JSONEncoder.shared.encode(written)
			try data.write(to: url, options: .atomic)
		} catch {
			log.error("Cannot write the shared reading: \(error.localizedDescription, privacy: .public)")
		}
	}
}

extension JSONEncoder {
	/// The encoder both sides use, so a date written by one is read by the other.
	static let shared: JSONEncoder = {
		let encoder = JSONEncoder()
		encoder.dateEncodingStrategy = .iso8601
		return encoder
	}()
}

extension JSONDecoder {
	/// The decoder both sides use, matching `JSONEncoder.shared`.
	static let shared: JSONDecoder = {
		let decoder = JSONDecoder()
		decoder.dateDecodingStrategy = .iso8601
		return decoder
	}()
}
