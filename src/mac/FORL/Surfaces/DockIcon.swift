//
//  DockIcon.swift
//  The dial the Dock shows.
//
//  The whole icon is drawn rather than badged: a badge is the red pill macOS
//  reserves for a count of things waiting, and a percentage is not that. It is
//  a dial in the color of the service with the reading inside it, and nothing
//  else: at the size the Dock actually draws an icon, the ring says what the
//  number is a share of and a name beside it would only take the number's room.
//
//  The icon is given before the app is ever put in the Dock, so the generic
//  application icon is never the one that appears while the app starts. The name
//  under the pointer is the process name, which is the reading rather than the
//  product, and is written again whenever the reading changes.
//

import AppKit
import SwiftUI

/// The size the icon is drawn at. It is redrawn at whatever size the Dock asks
/// for, so this is only the size it reports.
private let iconSize: CGFloat = 256

/// The icon body, as a share of the tile, and how much its corners are rounded,
/// which are the proportions of a macOS application icon.
private let bodyRatio: CGFloat = 0.86
private let cornerRatio: CGFloat = 0.2237

/// The app's Dock icon and the name beside it.
@MainActor
enum DockIcon {
	/// Put a reading on the Dock, and under the pointer.
	///
	/// - Parameters:
	///   - percent: Share of the window already used, or nil before a reading
	///     has arrived.
	///   - accent: The color the ring is struck in.
	///   - name: What the Dock should read under the pointer, such as
	///     "34% - Current session".
	/// - Returns: Nothing.
	static func show(percent: Double?, accent: Color, name: String) {
		NSApp.applicationIconImage = image(percent: percent, accent: accent)
		ProcessInfo.processInfo.processName = name
	}

	/// Return the icon for a reading.
	///
	/// - Parameters:
	///   - percent: Share of the window already used, or nil.
	///   - accent: The color the ring is struck in.
	/// - Returns: The icon, on a transparent background outside its own body.
	static func image(percent: Double?, accent: Color) -> NSImage {
		let renderer = ImageRenderer(content: DockIconView(percent: percent, accent: accent))
		renderer.scale = 2
		renderer.proposedSize = ProposedViewSize(width: iconSize, height: iconSize)
		return renderer.nsImage ?? NSImage(size: NSSize(width: iconSize, height: iconSize))
	}
}

/// The icon, drawn the same way every other dial in the app is.
private struct DockIconView: View {
	/// Share of the window already used, or nil.
	var percent: Double?
	/// The color the ring is struck in.
	var accent: Color

	var body: some View {
		ZStack {
			RoundedRectangle(cornerRadius: iconSize * bodyRatio * cornerRatio, style: .continuous)
				.fill(Color(red: 0.11, green: 0.11, blue: 0.12))
				.frame(width: iconSize * bodyRatio, height: iconSize * bodyRatio)

			Dial(percent: percent, accent: accent)
				.frame(width: iconSize * bodyRatio, height: iconSize * bodyRatio)
				.foregroundStyle(.white)
				.environment(\.colorScheme, .dark)
		}
		.frame(width: iconSize, height: iconSize)
	}
}
