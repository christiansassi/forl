//
//  PanelWindow.swift
//  The window the panel is drawn in.
//
//  A non-activating panel on a translucent material, so it opens over whatever
//  the user was doing without taking the foreground from it and closes as soon
//  as it loses key. It hangs under whatever opened it, or against the top right
//  corner of the screen when nothing did.
//

import AppKit
import SwiftUI

/// How far the panel sits from the item it opened under, and from the edge of
/// the screen when it has to be pushed back inside it.
private let anchorGap: CGFloat = 6
private let screenMargin: CGFloat = 8

/// A borderless panel that can take the keyboard without activating the app.
final class PanelWindow: NSPanel {
	/// Report that this window accepts the keyboard.
	///
	/// A borderless window refuses the keyboard by default, and this one has to
	/// take it: losing it is how the panel knows to close, and Escape is how the
	/// user closes it without clicking elsewhere.
	///
	/// - Returns: True, always.
	override var canBecomeKey: Bool { true }

	/// Close the panel when the user presses Escape.
	///
	/// - Parameter sender: Whatever sent the cancel, which this ignores.
	/// - Returns: Nothing.
	override func cancelOperation(_ sender: Any?) {
		orderOut(nil)
	}
}

/// The panel, built once and shown wherever it is asked for.
@MainActor
final class PanelController {
	private let window: PanelWindow

	/// Build the panel hidden, around the view it draws.
	///
	/// - Parameter store: Everything the app is showing.
	/// - Returns: Nothing.
	init(store: UsageStore) {
		window = PanelWindow(
			contentRect: NSRect(x: 0, y: 0, width: 320, height: 200),
			styleMask: [.borderless, .nonactivatingPanel],
			backing: .buffered,
			defer: false
		)
		window.isOpaque = false
		window.backgroundColor = .clear
		window.hasShadow = true
		window.level = .floating
		window.hidesOnDeactivate = false
		window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

		let hosting = NSHostingView(rootView: PanelView(store: store))
		hosting.sizingOptions = [.preferredContentSize]

		let effect = NSVisualEffectView()
		effect.material = .popover
		effect.blendingMode = .behindWindow
		effect.state = .active
		effect.wantsLayer = true
		effect.layer?.cornerRadius = 12
		effect.layer?.cornerCurve = .continuous
		effect.layer?.masksToBounds = true
		effect.addSubview(hosting)

		hosting.translatesAutoresizingMaskIntoConstraints = false
		NSLayoutConstraint.activate([
			hosting.leadingAnchor.constraint(equalTo: effect.leadingAnchor),
			hosting.trailingAnchor.constraint(equalTo: effect.trailingAnchor),
			hosting.topAnchor.constraint(equalTo: effect.topAnchor),
			hosting.bottomAnchor.constraint(equalTo: effect.bottomAnchor),
		])
		window.contentView = effect
	}

	/// Return whether the panel is on screen.
	///
	/// - Returns: True while the window is visible.
	var isVisible: Bool { window.isVisible }

	/// Open the panel, or close it when it is already open.
	///
	/// - Parameter anchor: The view to open under, or nil to open against the
	///   top right corner of the screen.
	/// - Returns: Nothing.
	func toggle(under anchor: NSView?) {
		if window.isVisible {
			window.orderOut(nil)
			return
		}
		show(under: anchor)
	}

	/// Put the panel on screen, under whatever opened it.
	///
	/// - Parameter anchor: The view to open under, or nil.
	/// - Returns: Nothing.
	func show(under anchor: NSView?) {
		window.layoutIfNeeded()
		place(under: anchor)
		window.makeKeyAndOrderFront(nil)
	}

	/// Take the panel off screen.
	///
	/// - Returns: Nothing.
	func hide() {
		window.orderOut(nil)
	}

	/// Put the panel under what opened it, kept inside the screen.
	///
	/// - Parameter anchor: The view to open under, or nil.
	/// - Returns: Nothing.
	private func place(under anchor: NSView?) {
		let size = window.frame.size
		guard let screen = window.screen ?? NSScreen.main else {
			return
		}
		let visible = screen.visibleFrame

		var left: CGFloat
		var top: CGFloat
		if let anchor, let anchorWindow = anchor.window {
			let box = anchorWindow.convertToScreen(anchor.convert(anchor.bounds, to: nil))
			left = box.midX - size.width / 2
			top = box.minY - anchorGap
		} else {
			left = visible.maxX - size.width - screenMargin
			top = visible.maxY - screenMargin
		}

		left = max(visible.minX + screenMargin, min(left, visible.maxX - size.width - screenMargin))
		let bottom = max(visible.minY + screenMargin, top - size.height)
		window.setFrameOrigin(NSPoint(x: left, y: bottom))
	}
}
