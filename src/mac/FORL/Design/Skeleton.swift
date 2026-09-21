//
//  Skeleton.swift
//  What a surface shows in the shape of a reading that has not arrived yet.
//
//  A provider is asked for its usage after the surface is already on screen, so
//  there is a moment with nothing to draw. The panel and the medium widget fill
//  it with the outline of the row they are about to show rather than with the
//  word "Loading": the layout settles once, and what appears in it is the
//  reading rather than a replacement for it.
//

import SwiftUI

/// One block standing in for a piece of text still on its way.
struct SkeletonBlock: View {
	/// How wide the block is, in points, or nil to take the width offered.
	var width: CGFloat?
	/// How tall the block is, in points.
	var height: CGFloat = 10

	var body: some View {
		RoundedRectangle(cornerRadius: 3, style: .continuous)
			.fill(.primary.opacity(0.12))
			.frame(width: width, height: height)
	}
}
