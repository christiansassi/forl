//
//  UsageBar.swift
//  A capsule filled from the left to a level.
//
//  The track and the fill are the same color at two opacities, so an empty bar
//  still says which reading it belongs to. This is the shape a row of the panel
//  and of the medium widget uses, where there is width to spare and no height;
//  the dial is the same idea where there is height and no width.
//

import SwiftUI

/// One usage bar.
struct UsageBar: View {
	/// Share of the window already used, 0 to 100, or nil before a reading has
	/// arrived, which draws an empty bar.
	var percent: Double?
	/// How tall the bar is, in points.
	var height: CGFloat = 5

	var body: some View {
		GeometryReader { geometry in
			let fraction = (percent ?? 0) / 100
			ZStack(alignment: .leading) {
				Capsule()
					.fill(Theme.trackColor(percent))
				Capsule()
					.fill(Theme.usageColor(percent ?? 0))
					.frame(width: max(0, geometry.size.width * fraction))
					.animation(Theme.gaugeMotion, value: fraction)
			}
		}
		.frame(height: height)
	}
}
