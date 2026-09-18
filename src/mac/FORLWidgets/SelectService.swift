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

	var displayRepresentation: DisplayRepresentation {
		DisplayRepresentation(title: "\(label)")
	}

	/// Every service the app knows, as entities.
	static var all: [ServiceEntity] {
		providerIdentities.map { ServiceEntity(id: $0.key, label: $0.label) }
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
		ServiceEntity.all.first
	}
}

/// What the widget's editor asks.
struct SelectServiceIntent: WidgetConfigurationIntent {
	static let title: LocalizedStringResource = "Choose a service"
	static let description = IntentDescription("Which service's usage this widget shows.")

	/// The service the user picked, or nil for whichever is signed in first.
	@Parameter(title: "Service")
	var service: ServiceEntity?
}
