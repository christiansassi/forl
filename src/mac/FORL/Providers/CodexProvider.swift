//
//  CodexProvider.swift
//  Read ChatGPT usage with the sign-in the app made for itself.
//
//  Calls the usage endpoint of the Codex backend with a token this app obtained
//  in the browser and keeps in the keychain, renewing it when it is close to
//  running out. The response reports two rolling windows, a five hour primary
//  and a seven day secondary, which map onto the session and weekly windows the
//  interface already knows, and it names the plan itself, so no second request
//  is needed. ChatGPT reports no split by product, so the panel simply has no
//  product section for this provider.
//
//  Every usage request also names the account, which the sign-in reports in the
//  claims of the identity token rather than as a field of its own.
//

import Foundation
import SwiftUI

/// The ChatGPT usage endpoint of the Codex backend.
struct CodexProvider: Provider {
	let identity = providerIdentity(for: "chatgpt")!

	private static let usageURL = URL(string: "https://chatgpt.com/backend-api/codex/usage")!
	private static let userAgent = "forl/1.0"
	private static let originator = "codex_cli_rs"

	/// Where the identity token keeps what this provider needs and a standard
	/// claim set does not carry.
	private static let authClaim = "https://api.openai.com/auth"
	private static let accountIDClaim = "chatgpt_account_id"

	/// The usage endpoint answers 403 for two quite different reasons: a sign-in
	/// that has really gone, and a request it declines to serve for the moment.
	/// A token it has only just issued is refused for three to four seconds, and
	/// the endpoint also refuses the odd request for no reason it gives, in
	/// bursts, so a refused reading is tried again over a few seconds before it
	/// is believed.
	private static let retryAttempts = 5
	private static let retryDelay: Duration = .seconds(1)

	/// The port is not a free choice: this is the one the provider accepts for
	/// this client, so a sign-in cannot start while something else holds it.
	let oauth = OAuthClient(
		key: "chatgpt",
		label: "ChatGPT",
		authorizeURL: "https://auth.openai.com/oauth/authorize",
		tokenURL: "https://auth.openai.com/oauth/token",
		// Public identifier of the application these endpoints were built for.
		clientID: "app_EMoamEEZ73f0CkXaXp7hrann",
		// openid for the identity token, which is the only place the account
		// this usage is billed against is named; offline_access for the refresh
		// token, without which a sign-in lasts an hour; email for the address
		// the settings show.
		scope: "openid email offline_access",
		redirectPort: 1455,
		redirectPath: "/auth/callback",
		// Without the first, the identity token names no account and the usage
		// endpoint has nothing to bill the request against.
		authorizeExtras: [
			"id_token_add_organizations": "true",
			"codex_cli_simplified_flow": "true",
		],
		headers: ["User-Agent": userAgent, "originator": originator]
	)

	/// Sign in to ChatGPT in the browser and store what comes back.
	///
	/// - Parameter onAddress: Called once with the address to sign in at and
	///   whether a browser was opened at it.
	/// - Returns: Who is now signed in.
	/// - Throws: `UsageError` when the sign-in was refused or not completed.
	func signIn(onAddress: @Sendable @escaping (String, Bool) -> Void) async throws -> String {
		let answer = try await OAuth.signIn(client: oauth, onAddress: onAddress)
		guard
			let token = answer["access_token"] as? String,
			!token.trimmingCharacters(in: .whitespaces).isEmpty
		else {
			throw UsageError.credentials(OAuth.rejectedMessage)
		}

		let claims = Self.identity(answer)
		let tokens = Tokens(
			accessToken: token,
			refreshToken: answer["refresh_token"] as? String ?? "",
			expiresAt: OAuth.expiresAt(answer),
			account: Self.accountName(claims),
			// The plan is left out because the usage response names it, so
			// keeping it here would be a second copy of something already
			// arriving.
			plan: "",
			extra: ["account_id": Self.accountID(claims)]
		)
		try TokenStore.save(key, tokens)
		return tokens.account
	}

	/// Take one ChatGPT usage reading.
	///
	/// A refusal is only reported as an expired sign-in when the token says it
	/// has expired. The endpoint refuses perfectly good tokens as well, in
	/// bursts and for a few seconds after issuing one, and taking it at its word
	/// would tell the user their sign-in had run out and open a sign-in they do
	/// not need. A refusal the token contradicts is reported as what it is, a
	/// request that did not go through, which leaves the last reading on screen
	/// and says nothing.
	///
	/// - Returns: The current reading.
	/// - Throws: `UsageError.authentication` when the sign-in has run out,
	///   `UsageError.request` when the endpoint refused a token that has not.
	func read() async throws -> UsageSnapshot {
		let tokens = try await OAuth.usable(client: oauth)
		var headers = [
			"Authorization": "Bearer \(tokens.accessToken)",
			"Accept": "application/json",
			"User-Agent": Self.userAgent,
			"originator": Self.originator,
		]
		if let accountID = tokens.extra["account_id"], !accountID.isEmpty {
			headers["chatgpt-account-id"] = accountID
		}

		for attempt in 0..<Self.retryAttempts {
			if attempt > 0 {
				try await Task.sleep(for: Self.retryDelay)
			}
			do {
				return Self.parse(try await HTTP.fetchJSON(url: Self.usageURL, headers: headers))
			} catch UsageError.authentication {
				continue
			}
		}

		if let expiry = JWT.expiry(tokens.accessToken), expiry > Date() {
			throw UsageError.request("The usage endpoint refused the request.")
		}
		throw UsageError.authentication(OAuth.expiredMessage)
	}

	/// Return the claims of the identity token in a token endpoint answer.
	///
	/// - Parameter answer: The token endpoint's answer.
	/// - Returns: The claims, empty when the answer carries no identity token or
	///   it cannot be decoded.
	private static func identity(_ answer: [String: Any]) -> [String: Any] {
		guard let token = answer["id_token"] as? String, !token.isEmpty else {
			return [:]
		}
		return JWT.claims(token)
	}

	/// Return the account every usage request must be made against.
	///
	/// - Parameter claims: The claims of the identity token.
	/// - Returns: The account id, or an empty string when the claims carry none.
	private static func accountID(_ claims: [String: Any]) -> String {
		section(claims, authClaim)[accountIDClaim] as? String ?? ""
	}

	/// Return who is signed in, as the settings should name them.
	///
	/// - Parameter claims: The claims of the identity token.
	/// - Returns: The email address, falling back to the name, or an empty
	///   string when the claims carry neither.
	private static func accountName(_ claims: [String: Any]) -> String {
		for field in ["email", "name"] {
			if let value = claims[field] as? String, !value.trimmingCharacters(in: .whitespaces).isEmpty {
				return value.trimmingCharacters(in: .whitespaces)
			}
		}
		return ""
	}

	/// Build a usage snapshot from a decoded ChatGPT usage response.
	///
	/// - Parameter document: The decoded JSON body returned by the endpoint.
	/// - Returns: The parsed reading. It always carries a session window,
	///   reading 0 percent when the response reports none.
	static func parse(_ document: [String: Any]) -> UsageSnapshot {
		let plan = (document["plan_type"] as? String ?? "unknown")
			.replacingOccurrences(of: "_", with: " ")
			.capitalized
		let rateLimit = section(document, "rate_limit")
		let session = window(rateLimit["primary_window"], key: sessionKey, label: sessionLabel)
		let weekly = window(rateLimit["secondary_window"], key: weeklyKey, label: weeklyLabel)

		let credits = section(document, "credits")
		let hasCredits = credits["has_credits"] as? Bool == true && credits["unlimited"] as? Bool != true

		return UsageSnapshot(
			fetchedAt: Date(),
			plan: plan,
			session: session ?? UsageWindow(key: sessionKey, label: sessionLabel, percent: 0),
			weekly: weekly,
			extraLabel: hasCredits ? "Credit balance" : "",
			extraPercent: hasCredits ? (credits["overage_limit_reached"] as? Bool == true ? 100 : 0) : nil
		)
	}

	/// Build a usage window from one of the rate limit windows.
	///
	/// - Parameters:
	///   - value: A window object such as primary_window.
	///   - key: Stable identifier to store on the window.
	///   - label: Human readable name to store on the window.
	/// - Returns: The window, or nil when the section is absent.
	private static func window(_ value: Any?, key: String, label: String) -> UsageWindow? {
		guard let entry = value as? [String: Any] else {
			return nil
		}
		return UsageWindow(
			key: key,
			label: label,
			percent: clampPercent(entry["used_percent"] as? Double),
			resetsAt: parseEpoch(entry["reset_at"])
		)
	}
}
