// Open the provider represented by a Control Center reading.

import AppIntents
import AppKit
import Foundation

struct OpenFORLIntent: AppIntent {
	static let title: LocalizedStringResource = "Open FORL"
	@Parameter(title: "Provider") var providerKey: String
	init() { providerKey = "claude" }
	init(providerKey: String) { self.providerKey = providerKey }
	@MainActor func perform() async throws -> some IntentResult {
		let key = providerIdentity(for: providerKey)?.key ?? "claude"
		_ = try await NSWorkspace.shared.open(URL(string: "forl://provider/\(key)")!, configuration: NSWorkspace.OpenConfiguration())
		return .result()
	}
}
