// Configurable Control Center reading, rendered as a miniature gauge symbol.

import AppIntents
import WidgetKit
import SwiftUI

@available(macOS 26.0, *)
struct UsageControl: ControlWidget {
	var body: some ControlWidgetConfiguration {
		AppIntentControlConfiguration(kind: "io.forl.control", provider: ControlProvider()) { entry in
			ControlWidgetButton(action: OpenFORLIntent(providerKey: entry.providerKey ?? "claude")) {
				// The gauge alone, with no title beside it. Control Center offers every
				// control all three tile sizes and gives a resized tile to the label,
				// so a wider tile leaves the space around the gauge empty rather than
				// filling it with words: the reading is the gauge, at every size.
				Image("ControlGauge-\(entry.providerKey ?? "claude")-\(entry.metric.map { String(Int(clampPercent($0.percent).rounded())) } ?? "none")")
					.accessibilityLabel("\(entry.label), \(entry.metric?.label ?? "Sign in"), \(entry.metric.map { Formatting.percent($0.percent) } ?? "No reading")")
			}
			.tint(entry.accent)
		}
		.displayName("Usage")
		.description("Choose a provider and usage reading.")
	}
}

@available(macOS 26.0, *)
struct SelectControlIntent: ControlConfigurationIntent {
	static let title: LocalizedStringResource = "Choose a reading"
	@Parameter(title: "Provider") var service: ServiceEntity?
	@Parameter(title: "Show", optionsProvider: ControlMetricOptions()) var metric: MetricEntity?
}

@available(macOS 26.0, *)
struct ControlMetricOptions: DynamicOptionsProvider {
	@IntentParameterDependency<SelectControlIntent>(\.$service) var configuration
	func results() async throws -> [MetricEntity] {
		MetricEntity.available(for: configuration?.service.id)
	}
}

@available(macOS 26.0, *)
struct ControlProvider: AppIntentControlValueProvider {
	func previewValue(configuration: SelectControlIntent) -> UsageEntry {
		let key = configuration.service?.id ?? "claude"
		let identity = providerIdentity(for: key)!
		return UsageEntry(date: Date(), providerKey: key, label: identity.label, symbolName: identity.symbolName, metric: Metric(key: sessionKey, label: sessionLabel, percent: 34, resetsAt: nil, group: .limit), message: "")
	}
	func currentValue(configuration: SelectControlIntent) async throws -> UsageEntry {
		UsageEntry.current(serviceKey: configuration.service?.id, metricID: configuration.metric?.id)
	}
}
