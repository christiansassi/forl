//
//  ClaudeProvider.swift
//  Read Claude usage with the sign-in the app made for itself.
//
//  Calls the endpoint behind the /usage command with a token this app obtained
//  in the browser and keeps in the keychain, renewing it when it is close to
//  running out, and turns the response into the value objects every surface
//  renders. The response carries both a set of named windows and a normalized
//  "limits" array; the array is preferred because it already gives a percentage
//  and a reset time for every window.
//
//  It names no plan, so the plan shown beside the product name comes from the
//  account endpoint, asked alongside every reading. That is one small extra
//  request a minute and it is what lets an upgrade show up without signing in
//  again.
//

import Foundation
import SwiftUI

/// The Claude usage endpoint and the account endpoint beside it.
struct ClaudeProvider: Provider {
	let identity = providerIdentity(for: "claude")!

	private static let usageURL = URL(string: "https://api.anthropic.com/api/oauth/usage")!
	private static let profileURL = URL(string: "https://api.anthropic.com/api/oauth/profile")!
	private static let userAgent = "forl/1.0"
	private static let betaHeader = "oauth-2025-04-20"

	private static let sessionKind = "session"
	private static let weeklyAllKind = "weekly_all"
	private static let weeklyScopedKind = "weekly_scoped"
	private static let unknownPlan = "Unknown"

	/// What the browser is sent to, and where a code or a refresh token is
	/// exchanged. The exchange is on the API host, which answers a plain client;
	/// the pages that serve the authorization form sit behind a bot check and
	/// are for the browser only.
	///
	/// Two scopes, which are what the usage and account endpoints need and no
	/// more. The tool these endpoints were built for also asks for the scope
	/// that mints API keys, for file upload, for MCP servers and for plugins; an
	/// app that reads one number has no business holding any of those.
	let oauth = OAuthClient(
		key: "claude",
		label: "Claude",
		authorizeURL: "https://claude.com/cai/oauth/authorize",
		tokenURL: "https://api.anthropic.com/v1/oauth/token",
		// Public identifier of the application these endpoints were built for.
		// A client that runs on the user's machine can hold no secret, which is
		// what the proof key in the flow is for.
		clientID: "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
		scope: "user:profile user:inference",
		// Any free loopback port is accepted, so one is asked for rather than
		// chosen: a fixed port is a port that can already be taken.
		redirectPort: anyPort,
		redirectPath: "/callback",
		// The authorization page hands back a code rather than a token.
		authorizeExtras: ["code": "true"],
		headers: ["User-Agent": userAgent]
	)

	/// Sign in to Claude in the browser and store what comes back.
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

		let profile = await self.profile(token: token)
		let tokens = Tokens(
			accessToken: token,
			refreshToken: answer["refresh_token"] as? String ?? "",
			expiresAt: OAuth.expiresAt(answer),
			account: Self.accountName(profile),
			plan: Self.planLabel(profile)
		)
		try TokenStore.save(key, tokens)
		return tokens.account
	}

	/// Take one Claude usage reading.
	///
	/// - Returns: The current reading.
	/// - Throws: `UsageError` when the sign-in cannot be used or the endpoint
	///   cannot be reached.
	func read() async throws -> UsageSnapshot {
		var tokens = try await OAuth.usable(client: oauth)
		// Both requests carry the same token and neither needs the other's
		// answer, so they go out together: asking for the plan first put a
		// second round trip in front of every reading.
		async let profileAnswer = self.profile(token: tokens.accessToken)
		async let usageAnswer = HTTP.fetchJSON(url: Self.usageURL, headers: Self.headers(token: tokens.accessToken))
		let profile = await profileAnswer
		var plan = tokens.plan.isEmpty ? Self.unknownPlan : tokens.plan

		if !profile.isEmpty {
			let fresh = Self.planLabel(profile)
			let name = Self.accountName(profile)
			if fresh != tokens.plan || name != tokens.account {
				// An upgrade, or a first reading after a sign-in that could not
				// reach the endpoint. Kept so the settings can name the account
				// offline.
				tokens.plan = fresh
				tokens.account = name
				tokens = (try? TokenStore.remember(key, tokens)) ?? tokens
			}
			plan = fresh
		}

		return Self.parse(try await usageAnswer, plan: plan)
	}

	/// Return the headers every authenticated Claude request carries.
	///
	/// - Parameter token: The bearer token to send.
	/// - Returns: The headers, ready to pass to the transport.
	private static func headers(token: String) -> [String: String] {
		[
			"Authorization": "Bearer \(token)",
			"anthropic-beta": betaHeader,
			"Accept": "application/json",
			"User-Agent": userAgent,
		]
	}

	/// Return what the account endpoint says about the signed-in account.
	///
	/// - Parameter token: The bearer token to ask with.
	/// - Returns: The decoded response, empty when it could not be had. Losing
	///   it costs the plan name beside the product; treating that as a failed
	///   reading would cost the reading itself.
	private func profile(token: String) async -> [String: Any] {
		(try? await HTTP.fetchJSON(url: Self.profileURL, headers: Self.headers(token: token))) ?? [:]
	}

	/// Return the plan as it is named to the user, including the multiplier.
	///
	/// A Max subscription comes in more than one size, and which one is in force
	/// decides what every percentage on screen is a percentage of, so the
	/// multiplier belongs next to the plan name. The rate limit tier names both;
	/// the flags on the account are read only when it names neither.
	///
	/// - Parameter profile: The decoded account endpoint response.
	/// - Returns: Text such as "Max 5x", or "Pro", or "Unknown".
	static func planLabel(_ profile: [String: Any]) -> String {
		let tier = section(profile, "organization")["rate_limit_tier"] as? String ?? ""
		if let parsed = parseTier(tier) {
			return parsed
		}
		let account = section(profile, "account")
		if account["has_claude_max"] as? Bool == true {
			return "Max"
		}
		if account["has_claude_pro"] as? Bool == true {
			return "Pro"
		}
		return unknownPlan
	}

	/// Return a rate limit tier name as the plan it stands for.
	///
	/// Tiers are named like "default_claude_max_5x": the plan, and for Max the
	/// multiplier.
	///
	/// - Parameter tier: The tier name the account endpoint reported.
	/// - Returns: The plan as the user reads it, or nil when the name does not
	///   have that shape.
	private static func parseTier(_ tier: String) -> String? {
		let prefix = "default_claude_"
		guard tier.hasPrefix(prefix) else {
			return nil
		}
		var parts = tier.dropFirst(prefix.count).split(separator: "_").map(String.init)
		guard !parts.isEmpty else {
			return nil
		}
		var multiplier = ""
		if let last = parts.last, last.hasSuffix("x"), Int(last.dropLast()) != nil {
			multiplier = last
			parts.removeLast()
		}
		guard !parts.isEmpty else {
			return nil
		}
		let name = parts.map(\.capitalized).joined(separator: " ")
		return multiplier.isEmpty ? name : "\(name) \(multiplier)"
	}

	/// Return who is signed in, as the settings should name them.
	///
	/// - Parameter profile: The decoded account endpoint response.
	/// - Returns: The email address, falling back to whichever name the response
	///   carries, or an empty string when it carries none.
	static func accountName(_ profile: [String: Any]) -> String {
		let account = section(profile, "account")
		for field in ["email", "display_name", "full_name"] {
			if let value = account[field] as? String, !value.trimmingCharacters(in: .whitespaces).isEmpty {
				return value.trimmingCharacters(in: .whitespaces)
			}
		}
		return ""
	}

	/// Build a usage snapshot from a decoded Claude usage response.
	///
	/// - Parameters:
	///   - document: The decoded JSON body returned by the usage endpoint.
	///   - plan: Plan name from the local sign-in.
	/// - Returns: The parsed reading. It always carries a session window,
	///   reading 0 percent when the response reports none.
	static func parse(_ document: [String: Any], plan: String) -> UsageSnapshot {
		var session: UsageWindow?
		var weekly: UsageWindow?
		var scoped: [UsageWindow] = []

		for entry in document["limits"] as? [[String: Any]] ?? [] {
			switch entry["kind"] as? String {
			case sessionKind where session == nil:
				session = window(entry, key: sessionKey, label: sessionLabel)
			case weeklyAllKind where weekly == nil:
				weekly = window(entry, key: weeklyKey, label: weeklyLabel)
			case weeklyScopedKind:
				let name = scopeName(entry["scope"])
				let label = name.isEmpty ? "Scoped limit \(scoped.count + 1) this week" : "\(name) this week"
				scoped.append(window(entry, key: "scoped_\(scoped.count)", label: label, scopeName: name))
			default:
				break
			}
		}

		if session == nil {
			session = named(document["five_hour"], key: sessionKey, label: sessionLabel)
		}
		if weekly == nil {
			weekly = named(document["seven_day"], key: weeklyKey, label: weeklyLabel)
		}

		var breakdown: [BreakdownRow] = []
		for row in section(document, "seven_day_breakdown")["rows"] as? [[String: Any]] ?? [] {
			let identifier = row["key"] as? String
			guard let name = (row["display_name"] as? String ?? identifier), !name.isEmpty else {
				continue
			}
			breakdown.append(BreakdownRow(
				key: identifier ?? name,
				label: name,
				percent: clampPercent(row["percent"] as? Double)
			))
		}

		let extra = section(document, "extra_usage")
		let enabled = extra["is_enabled"] as? Bool == true

		return UsageSnapshot(
			fetchedAt: Date(),
			plan: plan,
			session: session ?? UsageWindow(key: sessionKey, label: sessionLabel, percent: 0),
			weekly: weekly,
			scoped: scoped,
			breakdown: breakdown,
			extraLabel: enabled ? "Extra usage" : "",
			extraPercent: enabled ? clampPercent(extra["utilization"] as? Double) : nil
		)
	}

	/// Build a usage window from one entry of the limits array.
	///
	/// - Parameters:
	///   - entry: A single limit object from the usage document.
	///   - key: Stable identifier to store on the window.
	///   - label: Human readable name to store on the window.
	///   - scopeName: Name of the model the limit applies to, empty when it
	///     covers the whole account.
	/// - Returns: The window described by that entry.
	private static func window(
		_ entry: [String: Any],
		key: String,
		label: String,
		scopeName: String = ""
	) -> UsageWindow {
		UsageWindow(
			key: key,
			label: label,
			percent: clampPercent(entry["percent"] as? Double),
			resetsAt: parseTimestamp(entry["resets_at"]),
			scopeName: scopeName
		)
	}

	/// Build a usage window from one of the named top level sections.
	///
	/// - Parameters:
	///   - value: A section such as five_hour from the usage document.
	///   - key: Stable identifier to store on the window.
	///   - label: Human readable name to store on the window.
	/// - Returns: The window, or nil when the section is absent.
	private static func named(_ value: Any?, key: String, label: String) -> UsageWindow? {
		guard let entry = value as? [String: Any] else {
			return nil
		}
		return UsageWindow(
			key: key,
			label: label,
			percent: clampPercent(entry["utilization"] as? Double),
			resetsAt: parseTimestamp(entry["resets_at"])
		)
	}

	/// Return the name of the model or surface a scoped limit applies to.
	///
	/// - Parameter scope: The scope object of a limit entry.
	/// - Returns: The name, or an empty string when the scope carries none.
	private static func scopeName(_ scope: Any?) -> String {
		guard let scope = scope as? [String: Any] else {
			return ""
		}
		for field in ["model", "surface"] {
			if
				let holder = scope[field] as? [String: Any],
				let name = holder["display_name"] as? String,
				!name.trimmingCharacters(in: .whitespaces).isEmpty
			{
				return name.trimmingCharacters(in: .whitespaces)
			}
		}
		return ""
	}
}
