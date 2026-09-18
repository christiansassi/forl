//
//  PKCE.swift
//  Proof key for code exchange, which is what lets a client keep no secret.
//
//  An app installed on a user's machine cannot hold a client secret: anything
//  shipped with it is readable by anyone who has it. Instead of a secret, the
//  authorization request carries the hash of a freshly made random string and
//  the code exchange carries the string itself. An authorization code
//  intercepted on its way back is then worth nothing without the string, which
//  never left this process.
//
//  Values are base64 in the URL safe alphabet with the padding removed, which
//  is the encoding RFC 7636 specifies.
//

import CryptoKit
import Foundation

/// Length of the random material behind each value. The specification allows a
/// verifier of 43 to 128 characters; 32 bytes encodes to 43, which is the floor
/// and is already 256 bits. The state is the same length, not because it needs
/// to be, but because one of the endpoints answers "invalid request format" to
/// a shorter one and says nothing else about it.
private let randomBytes = 32

/// The proof key a sign-in carries.
enum PKCE {
	/// Return a fresh code verifier.
	///
	/// - Returns: 43 characters of URL safe base64, to be sent with the code
	///   exchange and never before it.
	static func verifier() -> String {
		encode(randomData())
	}

	/// Return a fresh state value.
	///
	/// The provider echoes this back with the code, and a redirect carrying
	/// anything else did not come from the request this process made.
	///
	/// - Returns: 43 characters of URL safe base64.
	static func state() -> String {
		encode(randomData())
	}

	/// Return the challenge that goes with a verifier.
	///
	/// - Parameter verifier: The verifier to hash, as `verifier()` returned it.
	/// - Returns: The SHA-256 hash of the verifier, encoded the same way, to be
	///   sent with the authorization request.
	static func challenge(for verifier: String) -> String {
		encode(Data(SHA256.hash(data: Data(verifier.utf8))))
	}

	/// Return fresh random bytes.
	///
	/// - Returns: `randomBytes` bytes from the system's random source.
	private static func randomData() -> Data {
		var bytes = [UInt8](repeating: 0, count: randomBytes)
		_ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
		return Data(bytes)
	}

	/// Return bytes in the URL safe base64 alphabet without padding.
	///
	/// - Parameter raw: The bytes to encode.
	/// - Returns: The encoded text, which contains no character needing
	///   escaping in a query string.
	private static func encode(_ raw: Data) -> String {
		raw.base64EncodedString()
			.replacingOccurrences(of: "+", with: "-")
			.replacingOccurrences(of: "/", with: "_")
			.replacingOccurrences(of: "=", with: "")
	}
}
