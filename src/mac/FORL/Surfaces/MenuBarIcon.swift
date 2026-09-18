//
//  MenuBarIcon.swift
//  The tank drawn beside a menu bar item's reading.
//
//  The reading itself is not drawn here. It is the item's own title, so the
//  system colors it for whichever bar it is on and sets it in the bar's own
//  type, and only the part that carries the app's own color is drawn.
//
//  The image redraws itself in the appearance of the bar it is on, which is why
//  the mark is asked for as a template and the tank's track is a label color:
//  moving the window to a display in another appearance then needs nothing.
//

import AppKit
import SwiftUI

/// Width of the tank, and how far it stands clear of the top and bottom of the
/// bar. A menu bar is 22 points tall and its items are set in against both.
private let tankWidth: CGFloat = 6
private let tankInset: CGFloat = 4

/// The mark that names the service, and the gap between it and the tank.
private let markSize: CGFloat = 13
private let markGap: CGFloat = 4

/// The image a menu bar item carries.
enum MenuBarIcon {
	/// Return the tank, with the service's mark ahead of it when asked for.
	///
	/// - Parameters:
	///   - percent: Share of the window already used, 0 to 100, or nil before a
	///     reading has arrived, which draws an empty tank.
	///   - accent: The color to fill the mark with, or nil for an item that
	///     carries no mark.
	///   - symbolName: Name of the mark in the asset catalog, or nil for an item
	///     that carries none.
	/// - Returns: The image, only as wide as what it draws.
	static func image(percent: Double?, accent: Color?, symbolName: String?) -> NSImage {
		let height = NSStatusBar.system.thickness
		let mark: NSImage? = symbolName.flatMap { NSImage(named: $0) }
		let lead = mark == nil ? 0 : markSize + markGap

		let image = NSImage(size: NSSize(width: lead + tankWidth, height: height), flipped: false) { _ in
			if let mark {
				let box = NSRect(x: 0, y: (height - markSize) / 2, width: markSize, height: markSize)
				mark.isTemplate = true
				// A mark whose own color is near white or near black would read
				// on one menu bar and vanish on the other, so an accent that is
				// not a color in its own right gives way to the label color.
				let tint = accent.flatMap(NSColor.init(_:)) ?? NSColor.labelColor
				tint.set()
				mark.draw(in: box, from: .zero, operation: .sourceOver, fraction: 1)
				box.fill(using: .sourceAtop)
			}

			let track = NSRect(
				x: lead,
				y: tankInset,
				width: tankWidth,
				height: height - 2 * tankInset
			)
			let radius = tankWidth / 2
			trackColor(percent).setFill()
			NSBezierPath(roundedRect: track, xRadius: radius, yRadius: radius).fill()

			guard let percent, percent > 0 else {
				return true
			}
			NSGraphicsContext.current?.saveGraphicsState()
			NSBezierPath(roundedRect: track, xRadius: radius, yRadius: radius).addClip()
			NSColor(Theme.usageColor(percent)).setFill()
			NSRect(
				x: track.minX,
				y: track.minY,
				width: track.width,
				height: track.height * percent / 100
			).fill()
			NSGraphicsContext.current?.restoreGraphicsState()
			return true
		}
		image.isTemplate = false
		return image
	}

	/// Return the color of the tank behind the reading.
	///
	/// - Parameter percent: Share of the window already used, or nil.
	/// - Returns: The ramp color at low opacity, or a gray when there is nothing
	///   to report: the ramp starts at green and a green tank would be claiming
	///   the limit is untouched at the moment the app does not know what it is.
	private static func trackColor(_ percent: Double?) -> NSColor {
		guard let percent else {
			return NSColor.tertiaryLabelColor
		}
		return NSColor(Theme.usageColor(percent)).withAlphaComponent(Theme.trackOpacity)
	}
}
