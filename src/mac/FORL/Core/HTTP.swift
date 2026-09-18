//
//  HTTP.swift
//  The requests the widget makes.
//
//  Both providers answer a plain authenticated GET with a JSON document, and
//  both renew a sign-in with a form encoded POST, so the two requests, the
//  mapping from a refusal to an error and the decoding live here once.
//

import Foundation

/// How long a request is given before it is abandoned, in seconds.
private let requestTimeout: TimeInterval = 15

/// The status codes that mean the token was not accepted, as opposed to the
/// request failing for a reason the user cannot do anything about.
private let rejectedStatuses: Set<Int> = [400, 401, 403]

/// The calls the widget makes over the network.
enum HTTP {
	/// Request a JSON document and return it decoded.
	///
	/// - Parameters:
	///   - url: The endpoint to read.
	///   - headers: Request headers, including the authorization header.
	/// - Returns: The decoded JSON object.
	/// - Throws: `UsageError.authentication` when the endpoint rejects the
	///   token, `UsageError.request` when it cannot be reached or answers with
	///   anything else.
	static func fetchJSON(url: URL, headers: [String: String]) async throws -> [String: Any] {
		var request = URLRequest(url: url, timeoutInterval: requestTimeout)
		request.httpMethod = "GET"
		for (name, value) in headers {
			request.setValue(value, forHTTPHeaderField: name)
		}
		return try await send(request)
	}

	/// Send a form encoded POST and return the decoded JSON answer.
	///
	/// This is the shape an OAuth token endpoint takes, which is the only POST
	/// the widget makes: the one that gets or renews a sign-in.
	///
	/// - Parameters:
	///   - url: The endpoint to post to.
	///   - fields: The form fields to send.
	///   - headers: Request headers to add, of which the user agent matters: an
	///     endpoint behind a bot check refuses a request that does not name the
	///     client making it.
	/// - Returns: The decoded JSON object.
	/// - Throws: `UsageError.authentication` when the endpoint refuses the
	///   request, `UsageError.request` when it cannot be reached.
	static func postForm(
		url: URL,
		fields: [String: String],
		headers: [String: String]
	) async throws -> [String: Any] {
		var request = URLRequest(url: url, timeoutInterval: requestTimeout)
		request.httpMethod = "POST"
		request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
		request.setValue("application/json", forHTTPHeaderField: "Accept")
		for (name, value) in headers {
			request.setValue(value, forHTTPHeaderField: name)
		}
		request.httpBody = Data(formEncode(fields).utf8)
		return try await send(request)
	}

	/// Return form fields as the body of a form encoded request.
	///
	/// - Parameter fields: The fields to encode.
	/// - Returns: The encoded body, with every name and value percent escaped.
	static func formEncode(_ fields: [String: String]) -> String {
		fields
			.map { "\(escape($0.key))=\(escape($0.value))" }
			.sorted()
			.joined(separator: "&")
	}

	/// Return one string percent escaped for a query string or a form body.
	///
	/// - Parameter value: The text to escape.
	/// - Returns: The escaped text, in which every character outside the
	///   unreserved set is a percent escape and a space is not a plus.
	static func escape(_ value: String) -> String {
		var allowed = CharacterSet.alphanumerics
		allowed.insert(charactersIn: "-._~")
		return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value
	}

	/// Make one request and return the decoded JSON body.
	///
	/// What an endpoint says about a refusal goes to the log rather than to the
	/// panel: "invalid_client" and "invalid_grant" mean very different things to
	/// whoever is debugging, and neither means anything to the user.
	///
	/// - Parameter request: The prepared request.
	/// - Returns: The decoded JSON object.
	/// - Throws: `UsageError`, never a transport error of its own.
	private static func send(_ request: URLRequest) async throws -> [String: Any] {
		let data: Data
		let response: URLResponse
		do {
			(data, response) = try await URLSession.shared.data(for: request)
		} catch let error as URLError where error.code == .timedOut {
			throw UsageError.request("Request timed out.")
		} catch {
			throw UsageError.request("Request failed: \(error.localizedDescription)")
		}

		guard let http = response as? HTTPURLResponse else {
			throw UsageError.request("Endpoint returned no status.")
		}
		guard (200..<300).contains(http.statusCode) else {
			let address = request.url?.absoluteString ?? "endpoint"
			FileHandle.standardError.write(
				Data("\(address) -> HTTP \(http.statusCode) \(reason(data))\n".utf8)
			)
			if rejectedStatuses.contains(http.statusCode) {
				throw UsageError.authentication("Sign-in expired.")
			}
			throw UsageError.request("Request failed with HTTP \(http.statusCode).")
		}

		guard
			let decoded = try? JSONSerialization.jsonObject(with: data),
			let document = decoded as? [String: Any]
		else {
			throw UsageError.request("Endpoint returned an unexpected payload shape.")
		}
		return document
	}

	/// Return what an endpoint said about a refusal, as short text.
	///
	/// - Parameter body: The bytes the endpoint returned with the refusal.
	/// - Returns: The error name the endpoint gave, or the start of its body.
	private static func reason(_ body: Data) -> String {
		if
			let decoded = try? JSONSerialization.jsonObject(with: body),
			let document = decoded as? [String: Any]
		{
			for field in ["error", "detail", "message"] {
				if let named = document[field] as? String, !named.isEmpty {
					return named
				}
			}
		}
		return String(decoding: body.prefix(200), as: UTF8.self)
	}
}
