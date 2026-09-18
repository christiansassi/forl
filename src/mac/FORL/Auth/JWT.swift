//
//  JWT.swift
//  Read what a JSON web token says about itself.
//
//  Only the payload is decoded, and only for what the app needs from it: when
//  the token expires, and, for ChatGPT, which account and plan it was issued
//  for. The signature is the endpoint's business. Nothing here is a security
//  check: a token this file has read is still only trusted because the endpoint
//  that issued it handed it over, and because the endpoint that receives it
//  will check the signature itself.
//

import Foundation

/// The part of a "header.payload.signature" token that carries the claims.
private let payloadPart = 1

/// The claims a token carries.
enum JWT {
	/// Return the claims a token carries.
	///
	/// - Parameter token: The encoded token.
	/// - Returns: The decoded claims, empty when the token is not a JSON web
	///   token or its payload cannot be decoded.
	static func claims(_ token: String) -> [String: Any] {
		let parts = token.split(separator: ".", omittingEmptySubsequences: false)
		guard parts.count > payloadPart else {
			return [:]
		}
		var encoded = String(parts[payloadPart])
			.replacingOccurrences(of: "-", with: "+")
			.replacingOccurrences(of: "_", with: "/")
		// The payload is base64 with its padding stripped, which the decoder
		// needs back before it will accept the text.
		encoded += String(repeating: "=", count: (4 - encoded.count % 4) % 4)
		guard
			let data = Data(base64Encoded: encoded),
			let decoded = try? JSONSerialization.jsonObject(with: data),
			let document = decoded as? [String: Any]
		else {
			return [:]
		}
		return document
	}

	/// Return the expiry claim of a token.
	///
	/// - Parameter token: The encoded token.
	/// - Returns: The moment the token stops being accepted, or nil when it
	///   carries no expiry or cannot be decoded.
	static func expiry(_ token: String) -> Date? {
		guard let seconds = claims(token)["exp"] as? Double, seconds > 0 else {
			return nil
		}
		return Date(timeIntervalSince1970: seconds)
	}
}
