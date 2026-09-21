//
//  TokenStore.swift
//  Where the app keeps the sign-ins it made for itself.
//
//  In a file inside the group container, readable and writable by this user and
//  nobody else. File storage was introduced for ad-hoc builds whose changing
//  code signatures prevented stable keychain access. Keep that storage format
//  when moving to development signing so existing sign-ins can be migrated.
//
//  The file therefore carries refresh tokens, which are the sign-in itself. It
//  is written with owner-only permissions, in a container only this user can
//  reach, which is the same protection the tools these endpoints were built for
//  give their own credential files.
//
//  Unlike a preference, a sign-in that cannot be written is reported. A renewal
//  retires the token it was given, so a token obtained and not stored is a
//  sign-in lost, and the user must be told to do it again rather than left
//  wondering why the reading stopped.
//

import Foundation
import os

/// The file inside the group container that holds every provider's sign-in.
private let tokensFile = "tokens.json"

/// Readable and writable by the owner, and by nobody else.
private let ownerOnly: [FileAttributeKey: Any] = [.posixPermissions: 0o600]

private let log = Logger(subsystem: "io.forl.app", category: "tokens")

/// One provider's stored sign-in.
struct Tokens: Codable, Sendable, Equatable {
	/// What is sent to the usage endpoint.
	var accessToken: String
	/// What is exchanged for a new access token. Empty when the provider issued
	/// none, which leaves signing in again the only way back.
	var refreshToken: String = ""
	/// When the access token stops being accepted, or nil when the provider said
	/// nothing about it.
	var expiresAt: Date?
	/// Who is signed in, as the settings show them, usually an email address.
	var account: String = ""
	/// The plan as the panel shows it, such as "Max 5x". Stored rather than
	/// looked up, so a reading costs one request.
	var plan: String = ""
	/// Anything one provider needs and the other does not, such as the account
	/// id ChatGPT wants on every usage request.
	var extra: [String: String] = [:]
}

/// The file the sign-ins are kept in.
enum TokenStore {
	/// Return the stored sign-in of one provider.
	///
	/// - Parameter providerKey: Key of the provider, such as "claude".
	/// - Returns: The sign-in, or nil when there is none stored or what is
	///   stored carries no access token, which are the same thing to a caller.
	static func load(_ providerKey: String) -> Tokens? {
		guard
			let tokens = all()[providerKey],
			!tokens.accessToken.trimmingCharacters(in: .whitespaces).isEmpty
		else {
			return nil
		}
		return tokens
	}

	/// Store the sign-in of one provider, leaving the other's alone.
	///
	/// - Parameters:
	///   - providerKey: Key of the provider, such as "claude".
	///   - tokens: The sign-in to store.
	/// - Returns: Nothing.
	/// - Throws: `UsageError.credentials` when the file cannot be written, which
	///   would lose the sign-in the caller has just obtained.
	static func save(_ providerKey: String, _ tokens: Tokens) throws {
		var document = all()
		document[providerKey] = tokens
		try write(document)
	}

	/// Forget one provider's sign-in, leaving the other's alone.
	///
	/// - Parameter providerKey: Key of the provider, such as "claude".
	/// - Returns: Nothing. A file that cannot be written leaves the sign-in in
	///   place, which the caller sees for itself the next time it loads.
	static func clear(_ providerKey: String) {
		var document = all()
		guard document.removeValue(forKey: providerKey) != nil else {
			return
		}
		try? write(document)
	}

	/// Store a sign-in and return it.
	///
	/// Used by a renewal, which changes the tokens and nothing the user sees.
	///
	/// - Parameters:
	///   - providerKey: Key of the provider, such as "claude".
	///   - tokens: The sign-in to store, already changed by the caller.
	/// - Returns: What was stored.
	/// - Throws: `UsageError.credentials` when the file cannot be written.
	@discardableResult
	static func remember(_ providerKey: String, _ tokens: Tokens) throws -> Tokens {
		try save(providerKey, tokens)
		return tokens
	}

	/// Return the file the sign-ins are kept in.
	///
	/// - Returns: The path, or nil on a build whose App Group entitlement is
	///   missing, which cannot store anything.
	private static func fileURL() -> URL? {
		SharedStore.containerURL()?.appendingPathComponent(tokensFile)
	}

	/// Return every stored sign-in, keyed by provider.
	///
	/// - Returns: What is on disk, empty when there is nothing or it cannot be
	///   read.
	private static func all() -> [String: Tokens] {
		guard
			let url = fileURL(),
			let data = try? Data(contentsOf: url),
			let document = try? JSONDecoder.shared.decode([String: Tokens].self, from: data)
		else {
			return [:]
		}
		return document
	}

	/// Write every stored sign-in, owner readable and no wider.
	///
	/// - Parameter document: What to store, keyed by provider.
	/// - Returns: Nothing.
	/// - Throws: `UsageError.credentials` when the file cannot be written.
	private static func write(_ document: [String: Tokens]) throws {
		guard let url = fileURL() else {
			throw UsageError.credentials("There is nowhere to store the sign-in.")
		}
		do {
			let data = try JSONEncoder.shared.encode(document)
			try data.write(to: url, options: .atomic)
			// Set after the write rather than before it, because an atomic write
			// replaces the file and would take its permissions with it.
			try FileManager.default.setAttributes(ownerOnly, ofItemAtPath: url.path)
		} catch let error as UsageError {
			throw error
		} catch {
			log.error("Cannot store the sign-in: \(error.localizedDescription, privacy: .public)")
			throw UsageError.credentials("The sign-in could not be stored.")
		}
	}
}
