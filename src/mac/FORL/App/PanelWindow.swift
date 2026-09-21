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

/// How long after the panel closes a click still counts as the click that
/// closed it, rather than a click asking for it again.
private let reopenGuard: TimeInterval = 0.25

/// Calculate the complete panel frame below an anchor on its own screen.
enum PanelPlacement {
	/// Fit the content below the menu bar, including screens with negative origins.
	///
	/// - Parameters:
	///   - height: The measured height of the current page.
	///   - visible: The screen area available outside the Dock and menu bar.
	///   - anchor: The clicked button in screen coordinates, or nil for Dock launches.
	/// - Returns: A frame inside the available screen area.
	static func frame(height: CGFloat, visible: NSRect, anchor: NSRect?) -> NSRect {
		let available = visible.insetBy(dx: screenMargin, dy: screenMargin)
		let top = min(available.maxY, max(available.minY + 1, anchor.map { $0.minY - anchorGap } ?? available.maxY))
		let width = min(CGFloat(320), available.width)
		let left = min(max(anchor.map { $0.midX - width / 2 } ?? available.maxX - width, available.minX), available.maxX - width)
		let fittedHeight = min(max(1, ceil(height)), top - available.minY)
		return NSRect(x: left, y: top - fittedHeight, width: width, height: fittedHeight)
	}
}

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
	private var hosting: NSHostingView<PanelView>!
	private weak var anchor: NSView?
	private var contentHeight: CGFloat = 200
	private var resizeScheduled = false
	private var anchorObservers: [NSObjectProtocol] = []
	private var keyObserver: NSObjectProtocol?
	private var hiddenAt: Date = .distantPast

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

		hosting = NSHostingView(rootView: PanelView(store: store) { [weak self] height in
			self?.scheduleResize(to: height)
		})
		hosting.sizingOptions = []

		let effect = NSVisualEffectView(frame: window.contentLayoutRect)
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

		// Losing the keyboard is the only signal the panel gets that the user
		// has moved on. A menu bar item can be clicked a second time to close
		// what it opened; a widget and a Control Center control cannot, so the
		// panel has to take itself off screen.
		keyObserver = NotificationCenter.default.addObserver(forName: NSWindow.didResignKeyNotification, object: window, queue: .main) { [weak self] _ in
			Task { @MainActor in
				self?.hide()
			}
		}
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
		if window.isVisible, self.anchor === anchor {
			hide()
			return
		}
		// Clicking the item the panel hangs under takes the keyboard away from
		// it, so the panel has already closed itself by the time the click is
		// delivered. Let that click be the one that closed it.
		if self.anchor === anchor, Date().timeIntervalSince(hiddenAt) < reopenGuard {
			return
		}
		show(under: anchor)
	}

	/// Put the panel on screen, under whatever opened it.
	///
	/// - Parameter anchor: The view to open under, or nil.
	/// - Returns: Nothing.
	func show(under anchor: NSView?) {
		self.anchor = anchor
		hiddenAt = .distantPast
		observeAnchor()
		place()
		window.contentView?.layoutSubtreeIfNeeded()
		window.makeKeyAndOrderFront(nil)
	}

	/// Reposition when macOS finishes laying out or moves the status item.
	private func observeAnchor() {
		anchorObservers.forEach { NotificationCenter.default.removeObserver($0) }
		anchorObservers.removeAll()
		guard let anchorWindow = anchor?.window else { return }
		for name in [NSWindow.didMoveNotification, NSWindow.didResizeNotification, NSWindow.didChangeScreenNotification] {
			anchorObservers.append(NotificationCenter.default.addObserver(forName: name, object: anchorWindow, queue: .main) { [weak self] _ in
				Task { @MainActor in
					guard let self, self.window.isVisible else { return }
					self.place()
				}
			})
		}
	}

	deinit {
		anchorObservers.forEach { NotificationCenter.default.removeObserver($0) }
		keyObserver.map { NotificationCenter.default.removeObserver($0) }
	}

	/// Resize after SwiftUI finishes measuring, without changing AppKit mid-layout.
	///
	/// - Parameter height: The full height of the current page before scrolling.
	private func scheduleResize(to height: CGFloat) {
		guard height.isFinite, height > 0 else { return }
		contentHeight = height
		guard !resizeScheduled else { return }
		resizeScheduled = true
		DispatchQueue.main.async { [weak self] in
			guard let self else { return }
			self.resizeScheduled = false
			self.place()
			self.window.contentView?.layoutSubtreeIfNeeded()
		}
	}

	/// Take the panel off screen.
	///
	/// - Returns: Nothing.
	func hide() {
		guard window.isVisible else {
			return
		}
		hiddenAt = Date()
		window.orderOut(nil)
	}

	/// Put the panel under what opened it, kept inside the screen.
	///
	/// - Returns: Nothing.
	private func place() {
		guard let screen = anchor?.window?.screen ?? NSScreen.main ?? window.screen else {
			return
		}
		var anchorFrame: NSRect?
		if let anchor, let anchorWindow = anchor.window {
			let box = anchorWindow.convertToScreen(anchor.convert(anchor.bounds, to: nil))
			// Status items can briefly report a zero-origin frame during launch.
			// Use the screen corner until macOS supplies the actual menu bar frame.
			if !box.isEmpty, box.intersects(screen.frame), box.maxY >= screen.visibleFrame.maxY {
				anchorFrame = box
			}
		}
		let frame = PanelPlacement.frame(height: contentHeight, visible: screen.visibleFrame, anchor: anchorFrame)
		if window.frame != frame {
			window.setFrame(frame, display: true)
		}
	}
}
