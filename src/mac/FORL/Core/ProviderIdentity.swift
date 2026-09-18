//
//  ProviderIdentity.swift
//  How a service is named and colored.
//
//  Split from the provider itself so the widget extension can draw a reading
//  without carrying the code that obtains one. The extension never signs in and
//  never calls an endpoint, so it has no business linking the keychain, the
//  loopback server or the token exchange; all it needs is what to call the
//  service and what color to draw it in.
//

import SwiftUI

/// What a surface needs to know about a service in order to draw it.
struct ProviderIdentity: Sendable, Equatable {
	/// Stable identifier used in storage and in window names.
	var key: String
	/// Product name shown beside the reading.
	var label: String
	/// Name of the mark inside the asset catalog.
	var symbolName: String
	/// Brand color, used for the mark and the dial but never for a value. A
	/// service whose mark is white has no color of its own that reads on both a
	/// light and a dark surface, so it takes the label color instead.
	var accent: Color
}

/// Every service the app knows, in the order the interface shows them.
let providerIdentities: [ProviderIdentity] = [
	ProviderIdentity(
		key: "claude",
		label: "Claude",
		symbolName: "ClaudeMark",
		accent: Color(red: 0xd9 / 255, green: 0x77 / 255, blue: 0x57 / 255)
	),
	ProviderIdentity(
		key: "chatgpt",
		label: "ChatGPT",
		symbolName: "ChatGPTMark",
		accent: .primary
	),
]

/// Return how one service is named and colored.
///
/// - Parameter key: One of the provider keys, such as "claude".
/// - Returns: The identity, or nil when no service has that key.
func providerIdentity(for key: String) -> ProviderIdentity? {
	providerIdentities.first { $0.key == key }
}
