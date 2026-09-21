//
//  HeroSurfaces.swift
//  The app's surfaces, drawn for a picture rather than for the screen.
//
//  The banner and the launch film show the same things, so what they show is
//  built once here. None of it is a drawing of the interface: the dial geometry,
//  the usage ramp, the bar and the formatting are the app's own, compiled from
//  the same files the app is built from. Only the readings are invented.
//

import AppKit
import SwiftUI

/// How large a mark is rasterized before it is scaled down to where it is used.
let markResolution: CGFloat = 512

/// Where the provider marks are read from, given once by whoever is drawing.
enum MarkSource {
	/// The directory holding one SVG per provider.
	nonisolated(unsafe) static var directory = URL(fileURLWithPath: ".")
}

/// The readings the scene shows, which are the only invented thing in it.
let claudeSession = Metric(key: sessionKey, label: "Current session", percent: 38, resetsAt: Date().addingTimeInterval(3 * 3600), group: .limit)
let claudeWeekly = Metric(key: weeklyKey, label: "This week", percent: 64, resetsAt: Date().addingTimeInterval(52 * 3600), group: .limit)
let claudeCode = Metric(key: "claude_code", label: "Claude Code", percent: 47, resetsAt: nil, group: .product)
let claudeChat = Metric(key: "chat", label: "Chats", percent: 21, resetsAt: nil, group: .product)
let chatgptSession = Metric(key: sessionKey, label: "Current session", percent: 12, resetsAt: Date().addingTimeInterval(2 * 3600), group: .limit)
let chatgptWeekly = Metric(key: weeklyKey, label: "This week", percent: 29, resetsAt: Date().addingTimeInterval(66 * 3600), group: .limit)

/// Return one provider's mark, ready to be tinted.
///
/// - Parameter key: Key of the provider, such as "claude".
/// - Returns: The mark as a template image, or nil when the file is missing.
func mark(_ key: String) -> NSImage? {
	let url = MarkSource.directory.appendingPathComponent("\(key).svg")
	guard let image = NSImage(contentsOf: url) else {
		return nil
	}
	// The file declares its size in em, which arrives as one point square. Left
	// at that, the mark is rasterized at one pixel and drawn as a block.
	image.size = NSSize(width: markResolution, height: markResolution)
	image.isTemplate = true
	return image
}

/// One provider's mark at a size, in a color.
struct Mark: View {
	/// Key of the provider the mark belongs to.
	var key: String
	/// The color to fill it with.
	var tint: Color
	/// How wide and tall it is, in points.
	var size: CGFloat

	var body: some View {
		if let image = mark(key) {
			Image(nsImage: image)
				.resizable()
				.renderingMode(.template)
				.scaledToFit()
				.foregroundStyle(tint)
				.frame(width: size, height: size)
		}
	}
}

/// The dial the small widget and the Control Center tile are built around.
struct HeroDial: View {
	/// The reading to draw, 0 to 100.
	var percent: Double
	/// How much of the reading is drawn, from 0 to 1, which is what lets a film
	/// run a dial up to its value instead of cutting to it.
	var fill: Double = 1
	/// Key of the provider the dial belongs to.
	var providerKey: String
	/// The color the filled part and the mark take.
	var accent: Color
	/// The width and height of the square the dial fills, in points.
	var edge: CGFloat

	var body: some View {
		let shown = clampPercent(percent) * fill
		let fraction = shown / 100
		ZStack {
			HeroArc()
				.stroke(accent.opacity(Theme.trackOpacity), style: StrokeStyle(lineWidth: edge * DialGeometry.stroke, lineCap: .round))
			HeroArc(fraction: fraction)
				.stroke(accent, style: StrokeStyle(lineWidth: edge * DialGeometry.stroke, lineCap: .round))
			Text("\(Int(shown.rounded()))")
				.font(.system(size: edge * 0.32, weight: .semibold, design: .rounded))
				.monospacedDigit()
			Mark(key: providerKey, tint: accent, size: edge * DialGeometry.markSize)
				.offset(y: edge * (DialGeometry.markCenterY - 0.5))
		}
		.frame(width: edge, height: edge)
	}
}

/// The open arc of a dial, drawn from the app's own geometry.
struct HeroArc: Shape {
	/// How much of the sweep to draw, from 0 to 1.
	var fraction: Double = 1

	/// Return the path of the arc inside a square.
	///
	/// - Parameter rect: The square the dial fills.
	/// - Returns: The arc, empty at a fraction of zero.
	func path(in rect: CGRect) -> Path {
		guard fraction > 0 else {
			return Path()
		}
		var path = Path()
		path.addArc(
			center: CGPoint(x: rect.midX, y: rect.midY),
			radius: min(rect.width, rect.height) * DialGeometry.radius,
			startAngle: .degrees(DialGeometry.startDegrees),
			endAngle: .degrees(DialGeometry.startDegrees + DialGeometry.sweepDegrees * fraction),
			clockwise: false
		)
		return path
	}
}

/// A surface of the app, on the card the page floats it on.
struct Card<Content: View>: View {
	/// How round the corners are, in points.
	var radius: CGFloat = 20
	/// What the card holds.
	@ViewBuilder var content: Content

	var body: some View {
		content
			.background {
				RoundedRectangle(cornerRadius: radius, style: .continuous)
					.fill(.white)
			}
			.overlay {
				RoundedRectangle(cornerRadius: radius, style: .continuous)
					.stroke(.black.opacity(0.06), lineWidth: 1)
			}
			.shadow(color: .black.opacity(0.10), radius: 26, y: 10)
	}
}

/// What one card is, in a word or two under it.
struct Caption: View {
	/// What the surface above is called.
	var text: String

	var body: some View {
		Text(text)
			.font(.system(size: 15, weight: .medium))
			.foregroundStyle(.black.opacity(0.45))
	}
}

/// One reading, as a menu bar item draws it.
struct BarItem: View {
	/// The reading to show.
	var metric: Metric
	/// How much of the reading is drawn, from 0 to 1.
	var fill: Double = 1
	/// Key of the provider it belongs to.
	var providerKey: String
	/// The color the mark takes.
	var accent: Color

	var body: some View {
		HStack(spacing: 5) {
			Mark(key: providerKey, tint: accent, size: 13)
			Capsule()
				.fill(.black.opacity(0.18))
				.frame(width: 6, height: 14)
				.overlay(alignment: .bottom) {
					Capsule()
						.fill(Theme.usageColor(metric.percent))
						.frame(width: 6, height: 14 * clampPercent(metric.percent * fill) / 100)
				}
			Text(Formatting.percent(metric.percent * fill))
				.font(.system(size: 13, weight: .medium))
				.monospacedDigit()
				.frame(width: 34, alignment: .leading)
		}
	}
}

/// The right hand end of the menu bar, which is the part the app writes in.
struct MenuBarStrip: View {
	/// How much of each reading is drawn, from 0 to 1.
	var fill: Double = 1

	var body: some View {
		HStack(spacing: 0) {
			BarItem(metric: claudeSession, fill: fill, providerKey: "claude", accent: providerIdentity(for: "claude")!.accent)
				.padding(.trailing, 16)
			BarItem(metric: chatgptSession, fill: fill, providerKey: "chatgpt", accent: .black)
				.padding(.trailing, 18)
			ForEach(["battery.75percent", "wifi", "switch.2"], id: \.self) { symbol in
				Image(systemName: symbol)
					.font(.system(size: 14))
					.padding(.trailing, 16)
			}
			Text("9:41")
				.font(.system(size: 14))
				.monospacedDigit()
		}
		.foregroundStyle(.black)
		.padding(.horizontal, 20)
		.frame(height: 52)
		.fixedSize()
	}
}

/// One row of the panel: a name, a bar and a percentage.
struct PanelRow: View {
	/// The reading to draw.
	var metric: Metric
	/// Whether the reset line is shown under it.
	var showsReset: Bool = true
	/// How much of the reading is drawn, from 0 to 1.
	var fill: Double = 1

	var body: some View {
		VStack(alignment: .leading, spacing: 2) {
			HStack(spacing: 10) {
				Text(metric.label)
					.font(.system(size: 13))
					.lineLimit(1)
					.frame(width: 138, alignment: .leading)
				UsageBar(percent: metric.percent * fill)
				Text(Formatting.percent(metric.percent * fill))
					.font(.system(size: 13))
					.monospacedDigit()
					.frame(width: 42, alignment: .trailing)
			}
			if showsReset, !Formatting.subtitle(metric).isEmpty {
				Text(Formatting.subtitle(metric))
					.font(.system(size: 11))
					.foregroundStyle(.secondary)
			}
		}
	}
}

/// The panel that opens from the menu bar, on whichever service it is showing.
struct PanelCard: View {
	/// Key of the provider whose tab is selected.
	var provider: String = "claude"
	/// How much of each reading is drawn, from 0 to 1.
	var fill: Double = 1
	/// Whether the week's split by product is shown under the limits.
	///
	/// Left out, the panel is the same height whichever service it is showing,
	/// which is what a film needs when it switches between them in front of the
	/// viewer: a card that grows moves everything that was pointing at it.
	var showsProducts: Bool = true

	var body: some View {
		let identity = providerIdentity(for: provider)!
		let accent = provider == "claude" ? identity.accent : Color.black
		let plan = provider == "claude" ? "Max 5x" : "Plus"
		VStack(alignment: .leading, spacing: 0) {
			HStack(spacing: 4) {
				tab(key: "chatgpt", label: "ChatGPT", accent: .black, selected: provider == "chatgpt")
				tab(key: "claude", label: "Claude", accent: providerIdentity(for: "claude")!.accent, selected: provider == "claude")
			}
			.padding(.bottom, 14)

			HStack(spacing: 8) {
				Mark(key: provider, tint: accent, size: 16)
				Text(identity.label)
					.font(.system(size: 13, weight: .semibold))
				Text(plan)
					.font(.system(size: 11))
					.foregroundStyle(.secondary)
				Spacer()
				Image(systemName: "gearshape.fill")
					.foregroundStyle(.secondary)
			}
			.padding(.bottom, 14)

			let limits = provider == "claude" ? [claudeSession, claudeWeekly] : [chatgptSession, chatgptWeekly]
			PanelRow(metric: limits[0], fill: fill)
			Spacer().frame(height: 14)
			PanelRow(metric: limits[1], fill: fill)

			if provider == "claude", showsProducts {
				Spacer().frame(height: 22)
				Text("This week's usage by product")
					.font(.system(size: 11, weight: .semibold))
					.foregroundStyle(.secondary)
					.padding(.bottom, 8)
				PanelRow(metric: claudeCode, showsReset: false, fill: fill)
				Spacer().frame(height: 10)
				PanelRow(metric: claudeChat, showsReset: false, fill: fill)
			}
			Spacer().frame(height: 22)

			Text("Next update in 47s")
				.font(.system(size: 11))
				.monospacedDigit()
				.foregroundStyle(.secondary)
		}
		.padding(16)
		.frame(width: 320)
	}

	/// Return one provider tab of the panel.
	///
	/// - Parameters:
	///   - key: Key of the provider the tab belongs to.
	///   - label: The product name on the tab.
	///   - accent: The provider's color.
	///   - selected: Whether the tab is the one being shown.
	/// - Returns: The tab.
	private func tab(key: String, label: String, accent: Color, selected: Bool) -> some View {
		HStack(spacing: 6) {
			Mark(key: key, tint: accent, size: 14)
			Text(label)
				.font(.system(size: 12, weight: selected ? .semibold : .regular))
		}
		.foregroundStyle(selected ? AnyShapeStyle(accent) : AnyShapeStyle(.secondary))
		.frame(maxWidth: .infinity)
		.padding(.vertical, 7)
		.background {
			RoundedRectangle(cornerRadius: 7, style: .continuous)
				.fill(selected ? accent.opacity(0.14) : .clear)
		}
		.overlay {
			RoundedRectangle(cornerRadius: 7, style: .continuous)
				.stroke(selected ? accent.opacity(0.35) : .clear, lineWidth: 1)
		}
	}
}

/// The small widget: the dial, in the square the system gives it.
///
/// The same height as the medium widget, so a pair of them sits level.
struct SmallWidget: View {
	/// Key of the provider the widget shows.
	var providerKey: String
	/// The color the dial and the mark take.
	var accent: Color
	/// The reading the widget shows.
	var metric: Metric
	/// How much of the reading is drawn, from 0 to 1.
	var fill: Double = 1

	var body: some View {
		HeroDial(percent: metric.percent, fill: fill, providerKey: providerKey, accent: accent, edge: widgetHeight - 44)
			.frame(width: widgetHeight, height: widgetHeight)
	}
}

/// How tall a widget is drawn, whichever size it is.
let widgetHeight: CGFloat = 160

/// The medium widget, which is the panel's row on the desktop.
struct MediumWidget: View {
	/// Key of the provider the widget shows.
	var providerKey: String
	/// The product name at the top.
	var label: String
	/// The color the mark takes.
	var accent: Color
	/// The reading the widget shows.
	var metric: Metric
	/// How much of the reading is drawn, from 0 to 1.
	var fill: Double = 1

	var body: some View {
		VStack(alignment: .leading, spacing: 0) {
			HStack(spacing: 8) {
				Mark(key: providerKey, tint: accent, size: 16)
				Text(label)
					.font(.system(size: 13, weight: .semibold))
				Spacer()
			}
			Spacer()
			Text(metric.label)
				.font(.system(size: 13))
			HStack(spacing: 10) {
				UsageBar(percent: metric.percent * fill)
				Text(Formatting.percent(metric.percent * fill))
					.font(.system(size: 15, weight: .semibold))
					.monospacedDigit()
			}
			.padding(.top, 6)
			Text(Formatting.subtitle(metric))
				.font(.system(size: 12, weight: .medium))
				.foregroundStyle(.primary.opacity(0.8))
				.padding(.top, 5)
			Spacer()
		}
		.padding(16)
		.frame(width: 340, height: widgetHeight)
	}
}

/// The Control Center card, with the app's control among the system's own.
struct ControlCenterCard: View {
	/// How much of the reading is drawn, from 0 to 1.
	var fill: Double = 1
	/// How far each tile has arrived, from 0 to 1, in the order they arrive.
	var tiles: [Double] = [1, 1, 1]
	/// A second service to put a control of its own beside the first, or nil to
	/// stand a system control there instead.
	var second: String? = nil

	var body: some View {
		let claude = providerIdentity(for: "claude")!
		HStack(spacing: 18) {
			tile(arrived: tiles[0]) {
				HeroDial(percent: claudeSession.percent, fill: fill, providerKey: "claude", accent: claude.accent, edge: 44)
			}
			tile(arrived: tiles[1]) {
				if let second {
					HeroDial(percent: chatgptSession.percent, fill: fill, providerKey: second, accent: .black, edge: 44)
				} else {
					Image(systemName: "wifi")
						.font(.system(size: 22, weight: .medium))
						.foregroundStyle(.black.opacity(0.75))
				}
			}
			tile(arrived: tiles[2]) {
				Image(systemName: "bolt.fill")
					.font(.system(size: 22, weight: .medium))
					.foregroundStyle(.black.opacity(0.75))
			}
		}
		.padding(22)
	}

	/// Return one round Control Center tile around a piece of content.
	///
	/// - Parameters:
	///   - arrived: How far the tile has arrived, from 0 to 1.
	///   - content: What the tile holds.
	/// - Returns: The tile.
	func tile<Content: View>(arrived: Double, @ViewBuilder content: () -> Content) -> some View {
		ZStack {
			Circle()
				.fill(.black.opacity(0.05))
				.overlay { Circle().stroke(.black.opacity(0.06), lineWidth: 1) }
			content()
		}
		.frame(width: 68, height: 68)
		.scaleEffect(0.62 + 0.38 * arrived)
		.opacity(arrived)
	}
}

