//
//  SelectService.swift
//  Which service a widget shows.
//
//  A widget is configured rather than told: the user adds one, presses Edit
//  Widget, and picks Claude or ChatGPT from a list. Two widgets can then sit
//  side by side, one per service, which is the thing the menu bar does by
//  running two items and the Dock cannot do at all.
//
//  Leaving the choice unset shows whichever service is signed in first, so a
//  widget dropped on the desktop says something useful before it has been
//  configured.
//

import AppIntents
import WidgetKit

/// One service, as the widget's editor lists it.
struct ServiceEntity: AppEntity {
	/// The provider key, which is also what the entity is looked up by.
	var id: String
	/// The product name the editor shows.
	var label: String

	static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Service")
	static let defaultQuery = ServiceQuery()

	/// The mark, the name and the plan, which is what the panel's own header shows.
	var displayRepresentation: DisplayRepresentation {
		guard let identity = providerIdentity(for: id) else {
			return DisplayRepresentation(title: "\(label)")
		}
		let plan = SharedStore.load().reading(for: id)?.snapshot?.plan ?? ""
		return DisplayRepresentation(
			title: "\(label)",
			subtitle: plan.isEmpty ? nil : "\(plan)",
			image: .init(named: identity.symbolName, isTemplate: true)
		)
	}

	/// Every service the app knows, as entities.
	static var all: [ServiceEntity] {
		providerIdentities.sorted { $0.label < $1.label }.map { ServiceEntity(id: $0.key, label: $0.label) }
	}
}

/// Answers the editor's questions about which services there are.
struct ServiceQuery: EntityQuery {
	/// Return the services with the given keys.
	///
	/// - Parameter identifiers: The provider keys the editor is asking about.
	/// - Returns: The matching services.
	func entities(for identifiers: [String]) async throws -> [ServiceEntity] {
		ServiceEntity.all.filter { identifiers.contains($0.id) }
	}

	/// Return every service, for the list the editor shows.
	///
	/// - Returns: Every service the app knows.
	func suggestedEntities() async throws -> [ServiceEntity] {
		ServiceEntity.all
	}

	/// Return the service a new widget starts on.
	///
	/// - Returns: The first service, so a widget that has never been configured
	///   still shows something.
	func defaultResult() async -> ServiceEntity? {
		let key = SharedStore.load().readings.first?.providerKey
		return ServiceEntity.all.first { $0.id == key } ?? ServiceEntity.all.first
	}
}

/// What the widget's editor asks.
struct SelectServiceIntent: WidgetConfigurationIntent {
	static let title: LocalizedStringResource = "Choose a service"
	static let description = IntentDescription("Which service's usage this widget shows.")

	/// The service the user picked, or nil for whichever is signed in first.
	@Parameter(title: "Provider")
	var service: ServiceEntity?

	/// A reading belonging to the selected provider, independent of menu-bar choices.
	@Parameter(title: "Show", optionsProvider: WidgetMetricOptions())
	var metric: MetricEntity?
}

/// A provider-qualified reading that can be stored in a widget configuration.
struct MetricEntity: AppEntity {
	var id: String
	var label: String
	static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Reading")
	static let defaultQuery = MetricQuery()

	/// The name of the reading, which is the whole of what the picker offers.
	var displayRepresentation: DisplayRepresentation {
		DisplayRepresentation(title: "\(label)")
	}

	/// List only the readings reported by the requested provider.
	/// - Parameter providerKey: The service selected in the editor.
	/// - Returns: Available readings, or the standard session and weekly choices before a poll.
	static func available(for providerKey: String?) -> [MetricEntity] {
		guard let key = providerKey ?? ServiceEntity.all.first?.id,
			providerIdentity(for: key) != nil else { return [] }
		return WidgetChoices.available(for: key).map { MetricEntity(id: "\(key)/\($0.key)", label: $0.label) }
	}
}

/// Resolve saved reading identifiers without consulting menu-bar preferences.
struct MetricQuery: EntityQuery {
	/// Restore valid saved identifiers, including temporarily unavailable metrics.
	/// - Parameter identifiers: Provider and metric identifiers from stored configurations.
	/// - Returns: Matching entities without switching to a different provider.
	func entities(for identifiers: [String]) async throws -> [MetricEntity] {
		identifiers.compactMap { identifier in
			let parts = identifier.split(separator: "/", maxSplits: 1).map(String.init)
			guard parts.count == 2, providerIdentity(for: parts[0]) != nil, !parts[1].isEmpty else { return nil }
			return MetricEntity.available(for: parts[0]).first { $0.id == identifier } ?? MetricEntity(id: identifier, label: parts[1])
		}
	}

	/// Return readings for the default signed-in provider.
	func suggestedEntities() async throws -> [MetricEntity] { MetricEntity.available(for: nil) }
}

/// Refresh the widget's reading list when the selected provider changes.
struct WidgetMetricOptions: DynamicOptionsProvider {
	@IntentParameterDependency<SelectServiceIntent>(\.$service) var configuration

	/// Return readings belonging to the service currently selected in Edit Widget.
	func results() async throws -> [MetricEntity] {
		MetricEntity.available(for: configuration?.service.id)
	}
}
