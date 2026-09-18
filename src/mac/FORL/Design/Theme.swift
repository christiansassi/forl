//
//  Theme.swift
//  Color and type for every surface.
//
//  Almost nothing is a fixed value. Label colors, separators and backgrounds are
//  asked of the system by name, so they follow the appearance the user is in and
//  the increased contrast setting without this file having to notice either.
//
//  Two colors are the app's own. A brand accent marks what belongs to the
//  product, the mark and the dial, and comes from the provider. The usage ramp
//  runs from green to red with the percentage, so a bar says how close to its
//  limit it is by color alone, without anyone having to read the number.
//

import SwiftUI

/// Stops of the usage ramp. A value between two stops is mixed from them, so a
/// gauge shifts continuously rather than jumping at a threshold.
private let usageRamp: [(stop: Double, color: (Double, Double, Double))] = [
	(0, (48, 209, 88)),
	(50, (227, 193, 59)),
	(75, (232, 145, 45)),
	(100, (255, 69, 58)),
]

/// The measurements and colors every surface shares.
enum Theme {
	/// Opacity of a gauge track, which is the gauge color laid over whatever is
	/// behind it.
	static let trackOpacity: Double = 0.22

	/// Opacity of a rule between two groups.
	static let hairlineOpacity: Double = 0.09

	/// Thickness of a dial's ring as a share of its own diameter, which is what
	/// Apple draws a battery dial at: thin enough to read as a gauge rather than
	/// as a donut.
	static let ringThickness: Double = 0.085

	/// How far across a dial the ring reaches, as a share of its square.
	static let ringRadius: Double = 0.36

	/// How a gauge moves. It settles without overshoot, because a usage reading
	/// that bounced past its value would be reporting something that never
	/// happened.
	static let gaugeMotion: Animation = .spring(duration: 0.4, bounce: 0)

	/// Return the ramp color for a usage percentage.
	///
	/// - Parameter percent: Share of a window already used, 0 to 100.
	/// - Returns: The color a gauge at that percentage is filled with.
	static func usageColor(_ percent: Double) -> Color {
		let value = clampPercent(percent)
		var previous = usageRamp[0]
		for entry in usageRamp {
			if value <= entry.stop {
				let span = entry.stop - previous.stop
				let ratio = span <= 0 ? 0 : (value - previous.stop) / span
				return Color(
					red: mix(previous.color.0, entry.color.0, ratio) / 255,
					green: mix(previous.color.1, entry.color.1, ratio) / 255,
					blue: mix(previous.color.2, entry.color.2, ratio) / 255
				)
			}
			previous = entry
		}
		let last = usageRamp[usageRamp.count - 1].color
		return Color(red: last.0 / 255, green: last.1 / 255, blue: last.2 / 255)
	}

	/// Return the color of a gauge track.
	///
	/// A gauge with nothing to report takes a gray track. The ramp starts at
	/// green, and a green gauge would be claiming the limit is untouched at the
	/// moment the app does not yet know what it is.
	///
	/// - Parameter percent: Share of the window already used, or nil when no
	///   reading has arrived.
	/// - Returns: The color to fill the whole length of the gauge with.
	static func trackColor(_ percent: Double?) -> Color {
		guard let percent else {
			return Color.primary.opacity(0.18)
		}
		return usageColor(percent).opacity(trackOpacity)
	}

	/// Return one component mixed between two stops.
	///
	/// - Parameters:
	///   - low: The component at the lower stop.
	///   - high: The component at the upper stop.
	///   - ratio: How far between them, 0 to 1.
	/// - Returns: The mixed component.
	private static func mix(_ low: Double, _ high: Double, _ ratio: Double) -> Double {
		low + (high - low) * ratio
	}
}
