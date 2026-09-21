//
//  GenerateLaunchFilm.swift
//  Draw the app's surfaces as a short film.
//
//  The banner says what the app has; this says it in the order someone meets it,
//  a line of text at a time, on the same white page the banner uses. Every
//  surface in it is the app's own, drawn from the files the app is built from,
//  and only the readings are invented.
//
//  There is no animation framework in here and no timeline object. A frame is a
//  function of one number, the second it falls on, so the film can be rendered
//  out of order, at any rate, and looks the same every time it is made.
//

import AVFoundation
import AppKit
import SwiftUI

/// The size of a frame in points, and how many are drawn for each second.
private let frameSize = CGSize(width: 960, height: 540)
private let framesPerSecond: Int32 = 60
/// How much larger each frame is rendered than it is laid out, which is what
/// takes a 960 point page to a 1920 pixel picture.
///
/// The page is laid out small on purpose. The surfaces are drawn at the size the
/// app draws them, so the smaller the page they sit on the more of the frame
/// they fill, and scaling the page rather than the drawing keeps the type as
/// sharp as the frame allows.
private let renderScale: CGFloat = 2

/// Return a value eased into and out of its ends.
///
/// - Parameter value: How far through, from 0 to 1.
/// - Returns: The same distance, slowed at both ends.
private func ease(_ value: Double) -> Double {
	let clamped = min(1, max(0, value))
	return clamped * clamped * (3 - 2 * clamped)
}

/// Return a value eased onto its end alone.
///
/// - Parameter value: How far through, from 0 to 1.
/// - Returns: The same distance, quick at the start and slowing into the end.
private func easeOut(_ value: Double) -> Double {
	let clamped = min(1, max(0, value))
	let left = 1 - clamped
	return 1 - left * left * left
}

/// Return a value eased past its end and back onto it.
///
/// - Parameter value: How far through, from 0 to 1.
/// - Returns: The same distance, overshot near the end and settled onto it.
private func bump(_ value: Double) -> Double {
	let clamped = min(1, max(0, value))
	let overshoot = 2.2
	let past = clamped - 1
	return 1 + (overshoot + 1) * past * past * past + overshoot * past * past
}

/// Return how far through a stretch of the film one moment is.
///
/// - Parameters:
///   - now: The second the frame falls on.
///   - start: When the stretch begins, in seconds.
///   - length: How long it lasts, in seconds.
/// - Returns: 0 before it, 1 after it, and the eased distance through it.
private func progress(_ now: Double, from start: Double, over length: Double) -> Double {
	ease((now - start) / length)
}

/// One thing shown for a stretch of the film, fading up and away.
private struct Beat<Content: View>: View {
	/// The second the frame falls on.
	var now: Double
	/// When the beat begins, in seconds.
	var start: Double
	/// How long it stays, in seconds.
	var length: Double
	/// What the beat shows.
	@ViewBuilder var content: Content

	/// How long the arrival and the departure take, in seconds.
	private let fade = 0.3

	var body: some View {
		let entering = progress(now, from: start, over: fade)
		let leaving = progress(now, from: start + length - fade, over: fade)
		let shown = entering * (1 - leaving)
		content
			.opacity(shown)
			.scaleEffect(0.96 + 0.04 * bump(entering))
			.blur(radius: 5 * (1 - entering))
	}
}

/// A line of the film, revealed a word at a time.
///
/// Each word arrives grey and settles to black, and the line grows as it goes:
/// a word that has not landed takes no room, so what is on screen stays in the
/// middle of the frame instead of sitting to one side of a gap waiting to fill.
private struct WordLine: View {
	/// What the line says.
	var text: String
	/// The second the frame falls on.
	var now: Double
	/// When the first word lands, in seconds.
	var start: Double
	/// How long each word waits behind the one before it, in seconds.
	var stagger: Double = 0.1
	/// How large the line is set, in points.
	var size: CGFloat = 34

	/// How long a word takes to settle from grey to black, in seconds.
	private let settle = 0.26

	var body: some View {
		let words = text.split(separator: " ").map(String.init)
		HStack(spacing: 0) {
			ForEach(Array(words.enumerated()), id: \.offset) { index, word in
				let landed = progress(now, from: start + Double(index) * stagger, over: settle)
				let gap = index == 0 ? 0 : size * 0.26
				Text(word)
					.font(.system(size: size, weight: .medium))
					.foregroundStyle(.black.opacity(0.3 + 0.7 * landed))
					.fixedSize()
					.padding(.leading, gap)
					.frame(width: (width(of: word) + gap) * landed, alignment: .leading)
					.clipped()
			}
		}
	}

	/// Return how wide one word is when it is fully out.
	///
	/// - Parameter word: The word to measure.
	/// - Returns: Its width in points, in the font the line is set in.
	private func width(of word: String) -> CGFloat {
		(word as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: size, weight: .medium)]).width
	}
}

/// One surface thrown out of the middle of the frame to its own place.
private struct Thrown<Content: View>: View {
	/// The second the frame falls on.
	var now: Double
	/// When the throw begins, in seconds.
	var start: Double
	/// Where it lands, measured from the middle of the frame in points.
	var to: CGSize
	/// How large it ends up, as a share of its drawn size.
	var scale: CGFloat
	/// How long it waits behind the throw, in seconds.
	var delay: Double
	/// How far it is turned where it lands, in degrees.
	var turn: Double = 0
	/// The surface being thrown.
	@ViewBuilder var content: Content

	var body: some View {
		let thrown = bump(progress(now, from: start + delay, over: 0.6))
		content
			.scaleEffect(scale * (0.35 + 0.65 * thrown))
			.rotationEffect(.degrees(turn * thrown))
			.offset(x: to.width * thrown, y: to.height * thrown)
			.opacity(min(1, thrown * 2))
	}
}

/// The pointer, moving to what it is about to click and then clicking it.
private struct Pointer: View {
	/// The second the frame falls on.
	var now: Double
	/// When it starts moving, in seconds.
	var start: Double
	/// Where it comes from, measured from the middle of what it is over.
	var from: CGSize
	/// Where it lands, measured the same way.
	var to: CGSize

	/// How long the trip takes, and how long it waits before pressing.
	private let travel = 0.5
	private let pause = 0.06

	var body: some View {
		// One curve, not two: running the eased distance through the eased clock
		// again left the pointer crawling away and crawling in.
		let moved = easeOut(min(1, max(0, (now - start) / travel)))
		let pressed = min(1, max(0, (now - start - travel - pause) / 0.08))
		let released = easeOut((now - start - travel - pause - 0.08) / 0.3)
		let ring = 8 + 30 * released
		// The box is a fixed size and the arrow is shifted inside it so that the
		// point of the arrow sits at the middle. Everything else, the ring and the
		// travel, is then measured from the point rather than from the picture.
		ZStack {
			Circle()
				.stroke(.black.opacity(0.22 * (1 - released)), lineWidth: 1.5)
				.frame(width: ring, height: ring)
				.opacity(pressed)
			Arrow()
				.fill(.black)
				.overlay { Arrow().stroke(.white, lineWidth: 1.2) }
				.frame(width: 15, height: 22)
				.offset(x: 7.5, y: 11)
				.scaleEffect(1 - 0.18 * pressed * (1 - released), anchor: .topLeading)
		}
		.frame(width: 60, height: 60)
		.offset(
			x: from.width + (to.width - from.width) * moved,
			y: from.height + (to.height - from.height) * moved
		)
		.opacity(easeOut((now - start + 0.2) / 0.25))
	}
}

/// The shape of the pointer itself.
private struct Arrow: Shape {
	/// Return the outline of the pointer inside a box.
	///
	/// - Parameter rect: The box the pointer is drawn in.
	/// - Returns: The outline, pointing at the top left corner.
	func path(in rect: CGRect) -> Path {
		let width = rect.width
		let height = rect.height
		var path = Path()
		path.move(to: CGPoint(x: 0, y: 0))
		path.addLine(to: CGPoint(x: 0, y: height * 0.78))
		path.addLine(to: CGPoint(x: width * 0.30, y: height * 0.60))
		path.addLine(to: CGPoint(x: width * 0.50, y: height))
		path.addLine(to: CGPoint(x: width * 0.70, y: height * 0.90))
		path.addLine(to: CGPoint(x: width * 0.50, y: height * 0.54))
		path.addLine(to: CGPoint(x: width * 0.86, y: height * 0.54))
		path.closeSubpath()
		return path
	}
}

/// The name, growing into the words it stands for.
///
/// It opens in two moves. First the four letters slide apart, each one holding
/// its place while the room its word needs appears behind it; then the words
/// themselves come in, whole. Nothing is ever shown half drawn, which is what
/// made a letter by letter reveal look broken rather than alive.
private struct NameExpansion: View {
	/// How far open it is, from 0 to 1.
	var opened: Double
	/// How large the name is set, in points.
	var size: CGFloat

	/// The initial that is always shown, and the rest of the word behind it.
	private let words = [("F", "ear"), ("O", "f"), ("R", "eaching"), ("L", "imits")]

	/// How much of the opening is spent making room before a word arrives.
	private let room = 0.5

	var body: some View {
		let spread = ease(min(1, opened / room))
		HStack(spacing: size * 0.34 * spread) {
			ForEach(Array(words.enumerated()), id: \.offset) { index, word in
				let inked = ease((opened - room - Double(index) * 0.06) / (1 - room - 0.18))
				HStack(spacing: 0) {
					Text(word.0)
					Text(word.1)
						.fixedSize()
						.opacity(inked)
						.frame(width: width(of: word.1) * spread, alignment: .leading)
				}
			}
		}
		.font(.system(size: size, weight: .semibold))
		.foregroundStyle(.black)
	}

	/// Return how wide a piece of the name is when it is fully out.
	///
	/// - Parameter text: The letters after the initial.
	/// - Returns: Their width in points, in the font the name is set in.
	private func width(of text: String) -> CGFloat {
		(text as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: size, weight: .semibold)]).width
	}
}

/// The film, as one frame of it.
///
/// Each shot is a beat with its own arrival: the readings run up to their value
/// rather than appearing at it, the pointer does what a person would do, and
/// every card drifts a little closer while it is on screen.
private struct Film: View {
	/// The second this frame falls on.
	var now: Double

	var body: some View {
		let claude = providerIdentity(for: "claude")!
		ZStack {
			Color(red: 0.97, green: 0.97, blue: 0.98)

			Beat(now: now, start: 0.15, length: 2.0) {
				WordLine(text: "Make the most of your plan.", now: now, start: 0.25)
			}

			// The panel, pushed in on while its readings run up.
			Beat(now: now, start: 2.1, length: 3.0) {
				let switched = now >= 3.62
				VStack(spacing: 20) {
					WordLine(text: "Every number, in front of you.", now: now, start: 2.2, size: 24)
					ZStack {
						Card(radius: 14) {
							PanelCard(
								provider: switched ? "claude" : "chatgpt",
								fill: switched ? progress(now, from: 3.62, over: 0.6) : progress(now, from: 2.4, over: 0.8),
								showsProducts: false
							)
						}
						.scaleEffect(0.82 + 0.18 * bump(progress(now, from: 2.25, over: 0.5)))
						Pointer(
							now: now,
							start: 2.9,
							from: CGSize(width: 150, height: 150),
							to: CGSize(width: 78, height: -80)
						)
					}
				}
			}

			// The bar drops in from the top of the screen, the way it sits on one,
			// and the pointer comes in and opens it.
			Beat(now: now, start: 5.0, length: 2.4) {
				VStack(spacing: 22) {
					WordLine(text: "In the menu bar.", now: now, start: 5.1, size: 24)
					Card(radius: 16) { MenuBarStrip(fill: progress(now, from: 5.2, over: 0.8)) }
						.scaleEffect(0.84 + 0.16 * bump(progress(now, from: 5.15, over: 0.45)))
				}
			}

			// Both widget sizes, arriving one after the other.
			Beat(now: now, start: 7.3, length: 2.2) {
				VStack(spacing: 20) {
					WordLine(text: "On the desktop.", now: now, start: 7.4, size: 24)
					HStack(spacing: 20) {
						Card(radius: 22) {
							SmallWidget(providerKey: "chatgpt", accent: .black, metric: chatgptSession, fill: progress(now, from: 7.7, over: 0.9))
						}
						.scaleEffect(0.8 + 0.2 * bump(progress(now, from: 7.55, over: 0.42)))
						Card(radius: 22) {
							MediumWidget(providerKey: "chatgpt", label: "ChatGPT", accent: .black, metric: chatgptWeekly, fill: progress(now, from: 7.9, over: 0.9))
						}
						.scaleEffect(0.8 + 0.2 * bump(progress(now, from: 7.72, over: 0.42)))
					}
					
				}
			}

			// The tiles arrive in order, the app's own first.
			Beat(now: now, start: 9.4, length: 2.0) {
				VStack(spacing: 20) {
					WordLine(text: "In Control Center.", now: now, start: 9.5, size: 24)
					Card(radius: 26) {
						ControlCenterCard(
							fill: progress(now, from: 9.9, over: 0.8),
							tiles: [
								bump(progress(now, from: 9.7, over: 0.32)),
								bump(progress(now, from: 9.84, over: 0.32)),
								bump(progress(now, from: 9.98, over: 0.32)),
							]
						)
					}
					.scaleEffect(0.84 + 0.16 * bump(progress(now, from: 9.55, over: 0.45)))
				}
			}

			// Every surface at once, thrown out of the middle of the frame and
			// ringed around the line that names what they have in common.
			Beat(now: now, start: 11.3, length: 2.6) {
				ZStack {
					Thrown(now: now, start: 11.4, to: CGSize(width: -250, height: -140), scale: 0.72, delay: 0, turn: -4) {
						Card(radius: 16) { MenuBarStrip() }
					}
					Thrown(now: now, start: 11.4, to: CGSize(width: 285, height: 120), scale: 0.46, delay: 0.06, turn: 3) {
						Card(radius: 14) { PanelCard() }
					}
					Thrown(now: now, start: 11.4, to: CGSize(width: 270, height: -135), scale: 0.72, delay: 0.12, turn: 4) {
						Card(radius: 22) {
							MediumWidget(providerKey: "chatgpt", label: "ChatGPT", accent: .black, metric: chatgptWeekly)
						}
					}
					Thrown(now: now, start: 11.4, to: CGSize(width: -285, height: 120), scale: 0.8, delay: 0.18, turn: -5) {
						Card(radius: 22) {
							SmallWidget(providerKey: "claude", accent: claude.accent, metric: claudeSession)
						}
					}
					Thrown(now: now, start: 11.4, to: CGSize(width: -10, height: 165), scale: 0.8, delay: 0.24, turn: 2) {
						Card(radius: 26) { ControlCenterCard(second: "chatgpt") }
					}
					Thrown(now: now, start: 11.4, to: CGSize(width: 25, height: -170), scale: 0.8, delay: 0.3, turn: -3) {
						Card(radius: 22) {
							SmallWidget(providerKey: "chatgpt", accent: .black, metric: chatgptSession)
						}
					}
					VStack(spacing: 10) {
						WordLine(text: "Everything under control.", now: now, start: 11.5, size: 26)
						Text("The limits, at least.")
							.font(.system(size: 15))
							.foregroundStyle(.black.opacity(0.4))
							.opacity(progress(now, from: 12.4, over: 0.4))
					}
				}
			}

			// The name, taken from four letters to what they stand for, and then
			// the advice that goes with a tool for watching a limit all day.
			Beat(now: now, start: 13.8, length: 3.4) {
				VStack(spacing: 18) {
					NameExpansion(opened: progress(now, from: 14.3, over: 1.2), size: 40)
					Text("But remember to touch grass sometimes :)")
						.font(.system(size: 15))
						.foregroundStyle(.black.opacity(0.4))
						.opacity(progress(now, from: 15.6, over: 0.45))
				}
			}
		}
		.frame(width: frameSize.width, height: frameSize.height)
		.environment(\.colorScheme, .light)
	}
}

/// Draw the film and write it out.
@main
@MainActor
enum GenerateLaunchFilm {
	/// How long the film runs, in seconds.
	static let duration = 16.8

	/// Return one frame of the film.
	///
	/// - Parameter second: The second the frame falls on.
	/// - Returns: The frame, or nil when the scene cannot be drawn.
	static func frame(at second: Double) -> CGImage? {
		let renderer = ImageRenderer(content: Film(now: second))
		renderer.scale = renderScale
		return renderer.cgImage
	}

	/// Write every frame into an H.264 file.
	///
	/// - Returns: Nothing. The process ends with a message on standard error
	///   when the arguments are wrong or the file cannot be written.
	static func main() async {
		guard CommandLine.arguments.count == 3 else {
			FileHandle.standardError.write(Data("Expected the shared asset directory and an output file\n".utf8))
			exit(1)
		}
		MarkSource.directory = URL(fileURLWithPath: CommandLine.arguments[1])
		let output = URL(fileURLWithPath: CommandLine.arguments[2])
		try? FileManager.default.removeItem(at: output)

		let width = Int(frameSize.width * renderScale)
		let height = Int(frameSize.height * renderScale)
		guard let writer = try? AVAssetWriter(outputURL: output, fileType: .mp4) else {
			FileHandle.standardError.write(Data("The file could not be opened for writing\n".utf8))
			exit(1)
		}
		let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
			AVVideoCodecKey: AVVideoCodecType.h264,
			AVVideoWidthKey: width,
			AVVideoHeightKey: height,
			AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 12_000_000],
		])
		input.expectsMediaDataInRealTime = false
		let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
			kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
			kCVPixelBufferWidthKey as String: width,
			kCVPixelBufferHeightKey as String: height,
		])
		writer.add(input)
		writer.startWriting()
		writer.startSession(atSourceTime: .zero)

		let total = Int(duration * Double(framesPerSecond))
		for index in 0..<total {
			guard let image = frame(at: Double(index) / Double(framesPerSecond)) else {
				FileHandle.standardError.write(Data("Frame \(index) could not be drawn\n".utf8))
				exit(1)
			}
			while !input.isReadyForMoreMediaData {
				try? await Task.sleep(for: .milliseconds(5))
			}
			guard let pool = adaptor.pixelBufferPool, let buffer = makeBuffer(image: image, pool: pool, width: width, height: height) else {
				FileHandle.standardError.write(Data("Frame \(index) could not be copied\n".utf8))
				exit(1)
			}
			adaptor.append(buffer, withPresentationTime: CMTime(value: CMTimeValue(index), timescale: framesPerSecond))
		}

		input.markAsFinished()
		await writer.finishWriting()
		if writer.status != .completed {
			FileHandle.standardError.write(Data("The film could not be written: \(writer.error?.localizedDescription ?? "unknown")\n".utf8))
			exit(1)
		}
	}

	/// Return one drawn frame as a buffer the writer takes.
	///
	/// - Parameters:
	///   - image: The frame as it was drawn.
	///   - pool: Where the writer's buffers come from.
	///   - width: Width of a frame in pixels.
	///   - height: Height of a frame in pixels.
	/// - Returns: The buffer, or nil when one cannot be had.
	static func makeBuffer(image: CGImage, pool: CVPixelBufferPool, width: Int, height: Int) -> CVPixelBuffer? {
		var buffer: CVPixelBuffer?
		guard CVPixelBufferPoolCreatePixelBuffer(nil, pool, &buffer) == kCVReturnSuccess, let buffer else {
			return nil
		}
		CVPixelBufferLockBaseAddress(buffer, [])
		defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
		guard
			let context = CGContext(
				data: CVPixelBufferGetBaseAddress(buffer),
				width: width,
				height: height,
				bitsPerComponent: 8,
				bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
				space: CGColorSpaceCreateDeviceRGB(),
				bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue
			)
		else {
			return nil
		}
		context.setFillColor(NSColor.white.cgColor)
		context.fill(CGRect(x: 0, y: 0, width: width, height: height))
		context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
		return buffer
	}
}
