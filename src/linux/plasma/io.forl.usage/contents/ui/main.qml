/*
 * The FORL widget for KDE Plasma 6.
 *
 * FORL writes every reading to ~/.cache/forl/status.json, and this widget reads
 * that file every few seconds and shows it in Plasma's own style, as the
 * applets of the system tray do: in a panel, each service's mark in the text
 * color of the theme with the percentage of each usage chosen for the tray
 * beside it, and on a click, or on the desktop, each service in turn with its
 * plan and one theme progress bar per usage chosen for the panel. Colors,
 * fonts and spacing come from the Plasma theme, so the widget follows Breeze,
 * light or dark, and any other theme.
 *
 * Whether FORL is running is asked of the session bus rather than read from the
 * file, which stays behind when FORL quits. Signing in and the settings stay in
 * FORL: those buttons ask FORL, through the bus, to open its own panel, which
 * starts FORL first when it is not running.
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
	property bool running: true
	property bool showPlan: true
	// Steps the countdown to the next reading while the readings are shown.
	property date now: new Date()

	// Whether FORL holds its name on the bus, then the file, read through a
	// shell so the cache directory follows XDG_CACHE_HOME.
	readonly property string statusCommand: 'dbus-send --session --print-reply=literal --dest=org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus.NameHasOwner string:io.forl.Usage; cat "${XDG_CACHE_HOME:-$HOME/.cache}/forl/status.json"'

	// Thresholds of the reading colors, as status.py gives the Waybar classes.
	readonly property real warningPercent: 50
	readonly property real criticalPercent: 80

	preferredRepresentation: Plasmoid.formFactor === PlasmaCore.Types.Planar ? fullRepresentation : compactRepresentation
	toolTipMainText: "FORL"
	toolTipSubText: compactText()

	// Return a service's usages that FORL shows in one place, "in_panel" or "in_tray".
	function usagesIn(service, place) {
		return (service.usages || []).filter(usage => usage[place])
	}

	// Return the services shown in the panel, with the usages chosen for the tray.
	function trayServices() {
		return services.filter(service => service.signed_in && usagesIn(service, "in_tray").length > 0)
	}

	// Return the one line of the tooltip, such as "Claude 23% 41%  ChatGPT 12%".
	function compactText() {
		if (!running) {
			return "FORL is not running"
		}
		const parts = trayServices().map(service => service.label + " " + usagesIn(service, "in_tray").map(usage => Math.round(usage.percent) + "%").join(" "))
		return parts.length > 0 ? parts.join("  ") : "FORL"
	}

	// Return the color of a reading: the theme's text color, then its neutral
	// color from half, then its negative color from 80%.
	function colorFor(percent) {
		if (percent >= criticalPercent) {
			return Kirigami.Theme.negativeTextColor
		}
		if (percent >= warningPercent) {
			return Kirigami.Theme.neutralTextColor
		}
		return Kirigami.Theme.textColor
	}

	// Return the line under a usage: what a per model limit covers, and when
	// the window resets, as FORL's panel words it.
	function subtitleFor(usage) {
		const lines = []
		if (usage.scope) {
			lines.push("Separate weekly limit for " + usage.scope)
		}
		if (usage.resets_at) {
			const reset = new Date(usage.resets_at)
			reset.setSeconds(reset.getSeconds() + 30, 0)
			const clock = reset.toLocaleTimeString(Qt.locale("en_US"), "h:mm AP")
			lines.push(reset.toDateString() === new Date().toDateString()
				? "Resets at " + clock
				: "Resets " + reset.toLocaleDateString(Qt.locale("en_US"), "dddd") + " " + clock)
		}
		return lines.join("\n")
	}

	// Return the line saying when the next reading comes, counted down here, or
	// whatever else FORL says there.
	function footerFor(service) {
		const status = service.status || ""
		if (service.next_update_at && status.startsWith("Next update in")) {
			const seconds = Math.max(0, Math.floor((new Date(service.next_update_at) - now) / 1000))
			return "Next update in " + seconds + "s"
		}
		return status
	}

	// Return the image of a provider mark.
	function markFor(service) {
		return Qt.resolvedUrl("../images/" + (service.logo || ""))
	}

	// Ask FORL to open its own panel on a service, or the tab last shown, in a
	// view, "usage" or "settings". The bus starts FORL when it is not running.
	function openForl(key, view) {
		runner.connectSource("dbus-send --session --type=method_call --dest=io.forl.Usage /io/forl/Usage io.forl.Usage.Open string:'" + key + "' string:" + view)
		root.expanded = false
	}

	P5Support.DataSource {
		id: reader
		engine: "executable"
		connectedSources: []
		onNewData: (source, data) => {
			const output = data["stdout"] || ""
			const lineEnd = output.indexOf("\n")
			root.running = output.slice(0, lineEnd).indexOf("true") >= 0
			try {
				const document = JSON.parse(output.slice(lineEnd + 1))
				root.services = document.services || []
				root.showPlan = document.show_plan !== false
			} catch (error) {
				// No file yet, or one being replaced: keep what is shown.
			}
			disconnectSource(source)
		}
	}

	P5Support.DataSource {
		id: runner
		engine: "executable"
		connectedSources: []
		onNewData: (source, data) => disconnectSource(source)
	}

	Timer {
		interval: 5000
		running: true
		repeat: true
		triggeredOnStart: true
		onTriggered: reader.connectSource(root.statusCommand)
	}

	Timer {
		interval: 1000
		running: root.expanded || Plasmoid.formFactor === PlasmaCore.Types.Planar
		repeat: true
		onTriggered: root.now = new Date()
	}

	compactRepresentation: MouseArea {
		id: compact
		readonly property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical
		Layout.minimumWidth: vertical ? 0 : compactRow.implicitWidth
		Layout.preferredWidth: vertical ? -1 : compactRow.implicitWidth
		Layout.minimumHeight: vertical ? compactRow.implicitHeight : 0
		onClicked: root.expanded = !root.expanded

		GridLayout {
			id: compactRow
			anchors.centerIn: parent
			flow: compact.vertical ? GridLayout.TopToBottom : GridLayout.LeftToRight
			columnSpacing: Kirigami.Units.largeSpacing
			rowSpacing: Kirigami.Units.smallSpacing

			Kirigami.Icon {
				visible: root.trayServices().length === 0
				Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
				Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
				source: Plasmoid.icon
			}

			Repeater {
				model: root.running ? root.trayServices() : []

				delegate: RowLayout {
					id: compactService
					required property var modelData
					spacing: Kirigami.Units.smallSpacing

					Kirigami.Icon {
						Layout.preferredWidth: Kirigami.Units.iconSizes.small
						Layout.preferredHeight: Kirigami.Units.iconSizes.small
						source: root.markFor(compactService.modelData)
						isMask: true
						color: Kirigami.Theme.textColor
					}

					Repeater {
						model: root.usagesIn(compactService.modelData, "in_tray")

						delegate: PlasmaComponents.Label {
							required property var modelData
							required property int index
							text: (index > 0 ? "· " : "") + Math.round(modelData.percent) + "%"
							color: modelData.percent >= root.criticalPercent ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
						}
					}
				}
			}
		}
	}

	fullRepresentation: ColumnLayout {
		Layout.preferredWidth: Kirigami.Units.gridUnit * 20
		Layout.minimumWidth: Kirigami.Units.gridUnit * 14
		spacing: Kirigami.Units.largeSpacing

		// While FORL is not running, the way to start it.
		ColumnLayout {
			visible: !root.running
			Layout.fillWidth: true
			spacing: Kirigami.Units.smallSpacing

			PlasmaComponents.Label {
				opacity: 0.7
				text: "FORL is not running"
			}

			PlasmaComponents.Button {
				icon.name: "media-playback-start"
				text: "Start FORL"
				onClicked: root.openForl("", "usage")
			}
		}

		PlasmaComponents.Label {
			visible: root.running && root.services.length === 0
			Layout.fillWidth: true
			wrapMode: Text.WordWrap
			opacity: 0.7
			text: "Start FORL to see your usage here."
		}

		Repeater {
			model: root.running ? root.services : []

			delegate: ColumnLayout {
				id: serviceColumn
				required property var modelData
				required property int index
				readonly property bool loading: (modelData.usages || []).length === 0 && modelData.status === "Loading"
				readonly property var shown: root.usagesIn(modelData, "in_panel")
				Layout.fillWidth: true
				spacing: Kirigami.Units.smallSpacing

				Kirigami.Separator {
					visible: serviceColumn.index > 0
					Layout.fillWidth: true
					Layout.bottomMargin: Kirigami.Units.smallSpacing
				}

				// The mark, the name and the plan. A click opens FORL on the service.
				PlasmaComponents.ItemDelegate {
					Layout.fillWidth: true
					onClicked: root.openForl(serviceColumn.modelData.key, "usage")
					contentItem: RowLayout {
						spacing: Kirigami.Units.smallSpacing

						Kirigami.Icon {
							Layout.preferredWidth: Kirigami.Units.iconSizes.small
							Layout.preferredHeight: Kirigami.Units.iconSizes.small
							source: root.markFor(serviceColumn.modelData)
							isMask: true
							color: Kirigami.Theme.textColor
						}

						Kirigami.Heading {
							Layout.fillWidth: true
							level: 4
							text: serviceColumn.modelData.label
						}

						PlasmaComponents.Label {
							visible: root.showPlan && !!serviceColumn.modelData.plan
							opacity: 0.6
							font: Kirigami.Theme.smallFont
							text: serviceColumn.modelData.plan || ""
						}
					}
				}

				PlasmaComponents.Button {
					visible: !serviceColumn.modelData.signed_in
					icon.name: "im-user"
					text: "Sign in to " + serviceColumn.modelData.label + "…"
					onClicked: root.openForl(serviceColumn.modelData.key, "usage")
				}

				// The usages the user chose to see, products after the limits.
				Repeater {
					model: serviceColumn.modelData.signed_in ? serviceColumn.shown : []

					delegate: ColumnLayout {
						id: usageColumn
						required property var modelData
						required property int index
						readonly property bool firstProduct: modelData.group === "product"
							&& (index === 0 || serviceColumn.shown[index - 1].group !== "product")
						Layout.fillWidth: true
						Layout.topMargin: Kirigami.Units.smallSpacing
						spacing: Kirigami.Units.smallSpacing / 2

						Kirigami.Heading {
							visible: usageColumn.firstProduct
							Layout.topMargin: Kirigami.Units.smallSpacing
							level: 5
							opacity: 0.7
							text: "This week's usage by product"
						}

						RowLayout {
							Layout.fillWidth: true

							PlasmaComponents.Label {
								Layout.fillWidth: true
								elide: Text.ElideRight
								text: usageColumn.modelData.label
							}

							PlasmaComponents.Label {
								font.bold: true
								color: root.colorFor(usageColumn.modelData.percent)
								text: Math.round(usageColumn.modelData.percent) + "%"
							}
						}

						PlasmaComponents.ProgressBar {
							Layout.fillWidth: true
							from: 0
							to: 100
							value: usageColumn.modelData.percent
						}

						PlasmaComponents.Label {
							visible: text !== ""
							Layout.fillWidth: true
							wrapMode: Text.WordWrap
							opacity: 0.6
							font: Kirigami.Theme.smallFont
							text: usageColumn.modelData.group === "product" ? "" : root.subtitleFor(usageColumn.modelData)
						}
					}
				}

				// Extra usage, beyond the plan, under its own heading.
				ColumnLayout {
					visible: serviceColumn.modelData.signed_in && !!(serviceColumn.modelData.extra && serviceColumn.modelData.extra.label)
					Layout.fillWidth: true
					Layout.topMargin: Kirigami.Units.smallSpacing
					spacing: Kirigami.Units.smallSpacing / 2

					RowLayout {
						Layout.fillWidth: true

						PlasmaComponents.Label {
							Layout.fillWidth: true
							elide: Text.ElideRight
							text: serviceColumn.modelData.extra ? serviceColumn.modelData.extra.label : ""
						}

						PlasmaComponents.Label {
							font.bold: true
							text: serviceColumn.modelData.extra ? Math.round(serviceColumn.modelData.extra.percent) + "%" : ""
						}
					}

					PlasmaComponents.ProgressBar {
						Layout.fillWidth: true
						from: 0
						to: 100
						value: serviceColumn.modelData.extra ? serviceColumn.modelData.extra.percent : 0
					}
				}

				// When the next reading comes, or what went wrong.
				RowLayout {
					visible: serviceColumn.modelData.signed_in || (serviceColumn.modelData.status && serviceColumn.modelData.status !== "Not signed in")
					Layout.fillWidth: true
					Layout.topMargin: Kirigami.Units.smallSpacing

					PlasmaComponents.Label {
						Layout.fillWidth: true
						wrapMode: Text.WordWrap
						opacity: 0.6
						font: Kirigami.Theme.smallFont
						text: serviceColumn.loading ? "Loading…" : root.footerFor(serviceColumn.modelData)
					}

					PlasmaComponents.BusyIndicator {
						visible: serviceColumn.loading || !!serviceColumn.modelData.refreshing
						Layout.preferredWidth: Kirigami.Units.iconSizes.small
						Layout.preferredHeight: Kirigami.Units.iconSizes.small
						running: visible
					}
				}
			}
		}

		Kirigami.Separator {
			visible: root.running && root.services.length > 0
			Layout.fillWidth: true
		}

		PlasmaComponents.ToolButton {
			visible: root.running && root.services.length > 0
			Layout.alignment: Qt.AlignRight
			icon.name: "configure"
			text: "FORL Settings…"
			onClicked: root.openForl("", "settings")
		}
	}
}
