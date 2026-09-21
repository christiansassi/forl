//
//  GenerateHeroImage.swift
//  Draw every surface of the app into one picture.
//
//  The README needs a banner, and what the app is cannot be said in one
//  screenshot: the readings live in the menu bar, in a panel, in two widget
//  sizes and in a Control Center tile, on two operating systems. So one scene is
//  composed here with all of them in it at once, on a desktop of its own.
//
//  Nothing here is a drawing of the interface. The dial geometry, the usage
//  ramp, the bar and the formatting are the app's own, compiled from the same
//  files the app is built from, so the banner cannot drift away from what the
//  app actually draws. Only the readings are invented.
//
//  The surfaces are laid out as a set of cards on a white page, each named
//  underneath, rather than as a photograph of one desktop: the app has surfaces
//  on two operating systems and what they have in common is the reading, not the
//  desktop any one of them sits on.
//

import AppKit
import SwiftUI

/// Size of the finished picture, in points. Rendered at twice this.
private let canvas = CGSize(width: 1500, height: 740)

/// Every surface of the app, on one page.
struct Hero: View {
	var body: some View {
		let claude = providerIdentity(for: "claude")!
		ZStack {
			Color(red: 0.96, green: 0.96, blue: 0.97)

			HStack(alignment: .center, spacing: 72) {
				VStack(spacing: 44) {
					surface("Menu bar") {
						Card(radius: 16) { MenuBarStrip() }
					}
					surface("Panel") {
						Card(radius: 14) { PanelCard() }
					}
				}

				VStack(spacing: 44) {
					surface("Widgets") {
						VStack(spacing: 24) {
							HStack(spacing: 24) {
								Card(radius: 22) {
									SmallWidget(providerKey: "claude", accent: claude.accent, metric: claudeWeekly)
								}
								Card(radius: 22) {
									MediumWidget(providerKey: "claude", label: "Claude", accent: claude.accent, metric: claudeWeekly)
								}
							}
							HStack(spacing: 24) {
								Card(radius: 22) {
									SmallWidget(providerKey: "chatgpt", accent: .black, metric: chatgptSession)
								}
								Card(radius: 22) {
									MediumWidget(providerKey: "chatgpt", label: "ChatGPT", accent: .black, metric: chatgptSession)
								}
							}
						}
					}
					surface("Control Center") {
						Card(radius: 26) { ControlCenterCard() }
					}
				}
			}
			.padding(.horizontal, 90)
		}
		.frame(width: canvas.width, height: canvas.height)
		.environment(\.colorScheme, .light)
	}

	/// Return one surface with its name under it.
	///
	/// - Parameters:
	///   - name: What the surface is called.
	///   - content: The surface itself.
	/// - Returns: The pair, laid out as one block.
	private func surface<Content: View>(_ name: String, @ViewBuilder content: () -> Content) -> some View {
		VStack(spacing: 14) {
			content()
			Caption(text: name)
		}
	}
}

/// Render the scene and write it out.
@main
@MainActor
enum GenerateHeroImage {
	/// Draw the scene and write the picture.
	///
	/// - Returns: Nothing. The process ends with a message on standard error
	///   when the arguments are wrong or the scene cannot be drawn.
	static func main() {
		guard CommandLine.arguments.count == 3 else {
			FileHandle.standardError.write(Data("Expected the shared asset directory and an output file\n".utf8))
			exit(1)
		}
		MarkSource.directory = URL(fileURLWithPath: CommandLine.arguments[1])
		let renderer = ImageRenderer(content: Hero())
		renderer.scale = 2
		guard
			let image = renderer.nsImage,
			let data = image.tiffRepresentation,
			let bitmap = NSBitmapImageRep(data: data),
			let png = bitmap.representation(using: .png, properties: [:])
		else {
			FileHandle.standardError.write(Data("The scene could not be rendered\n".utf8))
			exit(1)
		}
		try? png.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
	}
}
