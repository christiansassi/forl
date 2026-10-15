/*
 * The FORL widget for KDE Plasma 6.
 *
 * FORL writes every reading to ~/.cache/forl/status.json, and this widget reads
 * that file every half minute and shows it: on the desktop, each service with
 * the usages chosen for the panel, as bars; in a panel, one line with the usages
 * chosen for the tray, which opens the full view when clicked. It reads only
 * what FORL wrote, so FORL must be running for it to change.
 */

import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
	id: root

	// Every service as FORL last wrote it, in the order of its tabs.
	property var services: []
	// Read through a shell, so the cache directory follows XDG_CACHE_HOME.
	readonly property string statusCommand: 'cat "${XDG_CACHE_HOME:-$HOME/.cache}/forl/status.json"'

	preferredRepresentation: Plasmoid.formFactor === PlasmaCore.Types.Planar ? fullRepresentation : compactRepresentation
	toolTipMainText: "FORL"
	toolTipSubText: compactText()

	// Return a service's usages that FORL shows in one place, "in_panel" or "in_tray".
	function usagesIn(service, place) {
		return (service.usages || []).filter(usage => usage[place])
	}

	// Return the one line the panel form shows, such as "Claude 23% 41%  ChatGPT 12%".
	function compactText() {
		const parts = []
		for (const service of services) {
			if (!service.signed_in) {
				continue
			}
			const shown = usagesIn(service, "in_tray")
			const usages = shown.length > 0 ? shown : (service.usages || []).slice(0, 1)
			if (usages.length > 0) {
				parts.push(service.label + " " + usages.map(usage => Math.round(usage.percent) + "%").join(" "))
			}
		}
		return parts.length > 0 ? parts.join("  ") : "FORL"
	}

	// Return the color of a reading: green, then yellow from half, then red from 80%.
	function colorFor(percent) {
		if (percent >= 80) {
			return Kirigami.Theme.negativeTextColor
		}
		if (percent >= 50) {
			return Kirigami.Theme.neutralTextColor
		}
		return Kirigami.Theme.positiveTextColor
	}

	P5Support.DataSource {
		id: reader
		engine: "executable"
		connectedSources: []
		onNewData: (source, data) => {
			try {
				const document = JSON.parse(data["stdout"])
				root.services = document.services || []
			} catch (error) {
				// No file yet, or one being replaced: keep what is shown.
			}
			disconnectSource(source)
		}
	}

	Timer {
		interval: 30000
		running: true
		repeat: true
		triggeredOnStart: true
		onTriggered: reader.connectSource(root.statusCommand)
	}

	compactRepresentation: MouseArea {
		Layout.minimumWidth: compactLabel.implicitWidth
		Layout.preferredWidth: compactLabel.implicitWidth
		onClicked: root.expanded = !root.expanded

		PlasmaComponents.Label {
			id: compactLabel
			anchors.centerIn: parent
			text: root.compactText()
		}
	}

	fullRepresentation: ColumnLayout {
		Layout.preferredWidth: Kirigami.Units.gridUnit * 18
		Layout.minimumWidth: Kirigami.Units.gridUnit * 12
		spacing: Kirigami.Units.largeSpacing

		PlasmaComponents.Label {
			visible: root.services.length === 0
			Layout.fillWidth: true
			wrapMode: Text.WordWrap
			text: "Start FORL to see your usage here."
		}

		Repeater {
			model: root.services

			delegate: ColumnLayout {
				id: serviceColumn
				required property var modelData
				Layout.fillWidth: true
				spacing: Kirigami.Units.smallSpacing

				Kirigami.Heading {
					level: 4
					text: serviceColumn.modelData.label + (serviceColumn.modelData.plan ? "  " + serviceColumn.modelData.plan : "")
				}

				PlasmaComponents.Label {
					visible: !serviceColumn.modelData.signed_in
					opacity: 0.7
					text: "Not signed in"
				}

				Repeater {
					model: root.usagesIn(serviceColumn.modelData, "in_panel")

					delegate: RowLayout {
						id: usageRow
						required property var modelData
						Layout.fillWidth: true
						spacing: Kirigami.Units.smallSpacing

						PlasmaComponents.Label {
							Layout.fillWidth: true
							elide: Text.ElideRight
							text: usageRow.modelData.label
						}

						PlasmaComponents.ProgressBar {
							Layout.preferredWidth: Kirigami.Units.gridUnit * 7
							from: 0
							to: 100
							value: usageRow.modelData.percent
						}

						PlasmaComponents.Label {
							Layout.minimumWidth: Kirigami.Units.gridUnit * 2
							horizontalAlignment: Text.AlignRight
							color: root.colorFor(usageRow.modelData.percent)
							text: Math.round(usageRow.modelData.percent) + "%"
						}
					}
				}
			}
		}
	}
}
