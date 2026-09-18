//
//  ProviderMark.swift
//  The mark that says which service a surface belongs to.
//
//  Drawn from the asset catalog as a template image, so it takes whatever color
//  it is given rather than carrying one: the panel and the widgets tint it with
//  the provider's accent, and a surface whose background could be either light
//  or dark tints it with the label color instead, which is legible on both.
//

import SwiftUI

/// One provider's mark.
struct ProviderMark: View {
	/// Name of the image inside the asset catalog.
	var symbolName: String
	/// The color to fill it with.
	var tint: Color
	/// How wide and tall the mark is, in points.
	var size: CGFloat

	var body: some View {
		Image(symbolName)
			.renderingMode(.template)
			.resizable()
			.scaledToFit()
			.foregroundStyle(tint)
			.frame(width: size, height: size)
	}
}
