//
//  Dial.swift
//  A ring with the reading set inside it.
//
//  The reading starts at the top and runs clockwise, which is the direction a
//  dial is read in, and both ends are rounded so a small reading is a mark
//  rather than a sliver. The percent sign sits on the ring rather than under the
//  number, in a gap cut out of the ring for it, so the number keeps the whole
//  middle of the dial and the sign still says what the number is a share of.
//
//  Drawn by the Dock icon, by the small widget and by the Control Center
//  control, at three sizes and one shape.
//

import SwiftUI

/// A dial showing one reading.
struct Dial: View {
	/// Share of the window already used, 0 to 100, or nil before a reading has
	/// arrived, which draws an empty ring and a dash.
	var percent: Double?
	/// The color the ring is struck in.
	var accent: Color
	/// Whether to set the percent sign across the foot of the ring. False for a
	/// dial small enough that the sign would cost more than it says.
	var unit: Bool = true

	var body: some View {
		GeometryReader { geometry in
			let edge = min(geometry.size.width, geometry.size.height)
			let stroke = edge * Theme.ringRadius * 2 * Theme.ringThickness
			let fraction = (percent ?? 0) / 100

			ZStack {
				Circle()
					.inset(by: edge * (0.5 - Theme.ringRadius))
					.stroke(Theme.trackColor(percent), style: StrokeStyle(lineWidth: stroke))
					.mask(gapMask(edge: edge))

				Circle()
					.inset(by: edge * (0.5 - Theme.ringRadius))
					.trim(from: 0, to: fraction)
					.stroke(accent, style: StrokeStyle(lineWidth: stroke, lineCap: .round))
					.rotationEffect(.degrees(-90))
					.mask(gapMask(edge: edge))
					.animation(Theme.gaugeMotion, value: fraction)

				Text(percent.map { "\(Int($0.rounded()))" } ?? "-")
					.font(.system(size: edge * 0.30, weight: .semibold, design: .rounded))
					.monospacedDigit()
					.minimumScaleFactor(0.5)
					.lineLimit(1)

				if unit {
					Text("%")
						.font(.system(size: edge * 0.115, weight: .semibold, design: .rounded))
						.offset(y: edge * Theme.ringRadius)
				}
			}
			.frame(width: geometry.size.width, height: geometry.size.height)
		}
		.aspectRatio(1, contentMode: .fit)
	}

	/// Return the mask that keeps the ring out from behind the percent sign.
	///
	/// A full square with a small box punched out of the foot of it, so the sign
	/// sits in a break in the ring rather than on top of it.
	///
	/// - Parameter edge: The edge length of the dial's square, in points.
	/// - Returns: The mask to apply to the ring.
	@ViewBuilder
	private func gapMask(edge: CGFloat) -> some View {
		if unit {
			Rectangle()
				.overlay {
					Rectangle()
						.frame(width: edge * 0.22, height: edge * 0.17)
						.offset(y: edge * Theme.ringRadius)
						.blendMode(.destinationOut)
				}
				.compositingGroup()
		} else {
			Rectangle()
		}
	}
}
