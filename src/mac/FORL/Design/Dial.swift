// A usage number inside an open arc, with the provider mark in the bottom gap.

import SwiftUI

/// An open arc whose endpoints stay clear of the provider mark.
struct UsageArc: Shape {
	var fraction: Double = 1
	var animatableData: Double {
		get { fraction }
		set { fraction = newValue }
	}

	/// Draw the selected fraction of the 270-degree arc.
	/// - Parameter rect: The square containing the dial.
	/// - Returns: A path from the lower left around the top to the lower right.
	func path(in rect: CGRect) -> Path {
		let fraction = min(1, max(0, fraction))
		guard fraction > 0 else { return Path() }
		var path = Path()
		path.addArc(center: CGPoint(x: rect.midX, y: rect.midY), radius: min(rect.width, rect.height) * DialGeometry.radius, startAngle: .degrees(DialGeometry.startDegrees), endAngle: .degrees(DialGeometry.startDegrees + DialGeometry.sweepDegrees * fraction), clockwise: false)
		return path
	}
}

/// Show a number without a percent sign and a provider mark in the open gap.
struct Dial: View {
	var percent: Double?
	var accent: Color
	var symbolName: String
	@Environment(\.accessibilityReduceMotion) private var reduceMotion

	var body: some View {
		GeometryReader { geometry in
			let edge = min(geometry.size.width, geometry.size.height)
			let fraction = clampPercent(percent) / 100
			ZStack {
				UsageArc()
					.stroke(accent.opacity(Theme.trackOpacity), style: StrokeStyle(lineWidth: edge * DialGeometry.stroke, lineCap: .round))
				UsageArc(fraction: fraction)
					.stroke(accent, style: StrokeStyle(lineWidth: edge * DialGeometry.stroke, lineCap: .round))
					.animation(reduceMotion ? nil : Theme.gaugeMotion, value: fraction)
				Text(percent.map { "\(Int(clampPercent($0).rounded()))" } ?? "-")
					.font(.system(size: edge * 0.32, weight: .semibold, design: .rounded))
					.monospacedDigit()
					.lineLimit(1)
					.minimumScaleFactor(0.6)
					.frame(width: edge * 0.60)
				ProviderMark(symbolName: symbolName, tint: accent, size: edge * DialGeometry.markSize)
					.offset(y: edge * (DialGeometry.markCenterY - 0.5))
			}
			.frame(width: edge, height: edge)
			.frame(maxWidth: .infinity, maxHeight: .infinity)
		}
		.aspectRatio(1, contentMode: .fit)
		.accessibilityElement(children: .ignore)
		.accessibilityLabel(percent.map { Formatting.percent($0) } ?? "No reading")
	}
}
