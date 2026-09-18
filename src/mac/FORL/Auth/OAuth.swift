//
//  OAuth.swift
//  One OAuth client per provider, and the conversation held with it.
//
//  Both services accept the same flow, the authorization code flow with a proof
//  key that RFC 8252 defines for native applications, and differ only in their
//  addresses, their scopes and a handful of query parameters each wants. Those
//  differences are data, held in an OAuthClient, so the flow itself is written
//  once.
//
//  The client identifiers are not secrets. A public client cannot hold one,
//  which is the reason for the proof key, and both identifiers are shipped in
//  the command line tools these endpoints were built for.
//

import AppKit
import Foundation

/// How long the user has to finish signing in. Long enough to cover a password
/// manager, a second factor and a verification email.
private let signInTimeout: TimeInterval = 300

/// A token this close to running out is renewed rather than used. Wide enough
/// that a reading never starts with a token that expires while it is in flight.
private let renewalMargin: TimeInterval = 600

/// Everything one provider's authorization flow needs.
struct OAuthClient: Sendable {
	/// Provider key, which also names the keychain item the sign-in is kept in.
	var key: String
	/// Product name, used in what the user is told.
	var label: String
	/// Page the browser is sent to.
	var authorizeURL: String
	/// Endpoint a code or a refresh token is exchanged at.
	var tokenURL: String
	/// The public identifier of this application.
	var clientID: String
	/// Space separated scopes to ask for.
	var scope: String
	/// Loopback port the redirect comes back to, which must be one the provider
	/// accepts for this client, or `anyPort` when it accepts any.
	var redirectPort: UInt16
	/// Path of that redirect, such as "/callback".
	var redirectPath: String
	/// Query parameters this provider wants on the authorization request and
	/// the other does not.
	var authorizeExtras: [String: String] = [:]
	/// Request headers this provider wants on a token request, such as the user
	/// agent an endpoint behind a bot check insists on.
	var headers: [String: String] = [:]

	/// Return the redirect to name, for the port being listened on.
	///
	/// Written with "localhost" rather than the address actually listened on,
	/// because that is the spelling the providers accept, and the exchange
	/// compares the two as text: the same string must go in both requests.
	///
	/// - Parameter port: The port being listened on.
	/// - Returns: The redirect URI.
	func redirectURI(port: UInt16) -> String {
		"http://localhost:\(port)\(redirectPath)"
	}
}

/// The sign-in and the renewal, held with one provider at a time.
enum OAuth {
	static let rejectedMessage = "The provider refused the sign-in."
	static let expiredMessage = "Sign-in expired."
	static let notSignedInMessage = "Not signed in."

	/// Return the page to send the browser to.
	///
	/// The extras go first, which is where the tool these endpoints were built
	/// for puts the ones it sends. Order carries no meaning in a query string,
	/// but an endpoint that answers "invalid request format" and nothing more
	/// leaves no room to find out the hard way.
	///
	/// - Parameters:
	///   - client: The provider's client.
	///   - port: The loopback port being listened on.
	///   - challenge: The proof key challenge.
	///   - state: The value the provider must echo back.
	/// - Returns: The full authorization URL.
	static func authorizationURL(
		client: OAuthClient,
		port: UInt16,
		challenge: String,
		state: String
	) -> URL? {
		var fields = client.authorizeExtras
		fields["client_id"] = client.clientID
		fields["response_type"] = "code"
		fields["redirect_uri"] = client.redirectURI(port: port)
		fields["scope"] = client.scope
		fields["code_challenge"] = challenge
		fields["code_challenge_method"] = "S256"
		fields["state"] = state
		return URL(string: "\(client.authorizeURL)?\(HTTP.formEncode(fields))")
	}

	/// Run the whole sign-in: open the browser, catch the code, exchange it.
	///
	/// A browser that will not open is not the end of the attempt. The address
	/// is reported either way and the wait goes on, so whoever is watching can
	/// put it in front of the user to open by hand.
	///
	/// - Parameters:
	///   - client: The provider's client.
	///   - onAddress: Called once with the address to sign in at and whether a
	///     browser was opened at it.
	/// - Returns: The token endpoint's answer.
	/// - Throws: `UsageError.credentials` when the port is taken, the user did
	///   not finish, or the provider refused; `UsageError.request` when the
	///   token endpoint could not be reached.
	static func signIn(
		client: OAuthClient,
		onAddress: @Sendable @escaping (String, Bool) -> Void
	) async throws -> [String: Any] {
		let server = try LoopbackServer(port: client.redirectPort, path: client.redirectPath)
		defer { server.close() }
		try await server.start()

		let port = server.port
		let verifier = PKCE.verifier()
		let state = PKCE.state()
		guard let url = authorizationURL(
			client: client,
			port: port,
			challenge: PKCE.challenge(for: verifier),
			state: state
		) else {
			throw UsageError.credentials("The sign-in address could not be built.")
		}

		let opened = NSWorkspace.shared.open(url)
		onAddress(url.absoluteString, opened)

		let redirect = try await server.wait(timeout: signInTimeout)
		if !redirect.error.isEmpty {
			throw UsageError.credentials(rejectedMessage)
		}
		guard redirect.state == state else {
			throw UsageError.credentials("The sign-in answer did not match the request.")
		}
		guard !redirect.code.isEmpty else {
			throw UsageError.credentials("Sign-in was not completed.")
		}
		return try await exchange(client: client, port: port, code: redirect.code, verifier: verifier, state: state)
	}

	/// Exchange an authorization code for tokens.
	///
	/// The state goes with the exchange as well as with the authorization
	/// request, which is not what the specification asks for: state is meant to
	/// be the client's own business, checked when the redirect comes back. One
	/// of the two endpoints refuses the exchange outright without it, and the
	/// other ignores it, so it is always sent.
	///
	/// - Parameters:
	///   - client: The provider's client.
	///   - port: The loopback port the authorization request named.
	///   - code: The code the redirect carried.
	///   - verifier: The verifier whose challenge went with the request.
	///   - state: The state that went with the request.
	/// - Returns: The token endpoint's answer.
	/// - Throws: `UsageError.credentials` when the endpoint refuses the code.
	static func exchange(
		client: OAuthClient,
		port: UInt16,
		code: String,
		verifier: String,
		state: String
	) async throws -> [String: Any] {
		try await tokenRequest(client: client, fields: [
			"grant_type": "authorization_code",
			"code": code,
			"client_id": client.clientID,
			"redirect_uri": client.redirectURI(port: port),
			"code_verifier": verifier,
			"state": state,
		])
	}

	/// Exchange a refresh token for a new access token.
	///
	/// - Parameters:
	///   - client: The provider's client.
	///   - refreshToken: The stored refresh token.
	/// - Returns: The token endpoint's answer. Both providers retire the refresh
	///   token they are given and return a new one, so the caller must store the
	///   answer before using it.
	/// - Throws: `UsageError.credentials` when the endpoint refuses the refresh
	///   token, which means the sign-in must be done again.
	static func renew(client: OAuthClient, refreshToken: String) async throws -> [String: Any] {
		try await tokenRequest(client: client, fields: [
			"grant_type": "refresh_token",
			"refresh_token": refreshToken,
			"client_id": client.clientID,
			"scope": client.scope,
		])
	}

	/// Return when the access token in a token answer stops being accepted.
	///
	/// Two providers say this two different ways. One returns the lifetime in
	/// seconds, the other returns a token that carries its own expiry, so both
	/// are tried before giving up and letting the endpoint be the judge.
	///
	/// - Parameter answer: A token endpoint's answer.
	/// - Returns: The moment, or nil when nothing in the answer says.
	static func expiresAt(_ answer: [String: Any]) -> Date? {
		if let lifetime = answer["expires_in"] as? Double, lifetime > 0 {
			return Date().addingTimeInterval(lifetime)
		}
		guard let access = answer["access_token"] as? String else {
			return nil
		}
		return JWT.expiry(access)
	}

	/// Return the stored sign-in, with an access token good for the next request.
	///
	/// A token near its end is renewed here rather than at the endpoint's
	/// refusal, so a reading never starts with one that expires while it is in
	/// flight. The answer is written back before it is used: both providers
	/// retire the refresh token they are given, so one obtained and not stored
	/// is a sign-in lost.
	///
	/// - Parameter client: The provider's client.
	/// - Returns: The sign-in, whose access token is current.
	/// - Throws: `UsageError.credentials` when nothing is stored, or the sign-in
	///   has run out and cannot be renewed.
	static func usable(client: OAuthClient) async throws -> Tokens {
		guard let tokens = TokenStore.load(client.key) else {
			throw UsageError.credentials(notSignedInMessage)
		}
		guard let expiry = tokens.expiresAt else {
			return tokens
		}
		guard expiry.timeIntervalSinceNow < renewalMargin else {
			return tokens
		}
		guard !tokens.refreshToken.trimmingCharacters(in: .whitespaces).isEmpty else {
			throw UsageError.credentials(expiredMessage)
		}

		let answer = try await renew(client: client, refreshToken: tokens.refreshToken)
		guard
			let access = answer["access_token"] as? String,
			!access.trimmingCharacters(in: .whitespaces).isEmpty
		else {
			throw UsageError.credentials(expiredMessage)
		}
		var renewed = tokens
		renewed.accessToken = access
		if let fresh = answer["refresh_token"] as? String, !fresh.isEmpty {
			renewed.refreshToken = fresh
		}
		renewed.expiresAt = expiresAt(answer)
		return try TokenStore.remember(client.key, renewed)
	}

	/// Post to the token endpoint and return what it answers.
	///
	/// The transport maps a refusal to the error a reading would raise, which is
	/// not what a refusal means here: a code this endpoint rejects is a sign-in
	/// that did not happen, not one that ran out. It is translated on the way
	/// out.
	///
	/// - Parameters:
	///   - client: The provider's client.
	///   - fields: The form fields to send.
	/// - Returns: The decoded answer.
	/// - Throws: `UsageError.credentials` when the endpoint refuses the request.
	private static func tokenRequest(
		client: OAuthClient,
		fields: [String: String]
	) async throws -> [String: Any] {
		guard let url = URL(string: client.tokenURL) else {
			throw UsageError.credentials("The token endpoint address is not a URL.")
		}
		do {
			return try await HTTP.postForm(url: url, fields: fields, headers: client.headers)
		} catch UsageError.authentication {
			throw UsageError.credentials(rejectedMessage)
		}
	}
}
