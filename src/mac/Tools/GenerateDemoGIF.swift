//
//  GenerateDemoGIF.swift
//  Turn the launch film into the picture a README can play.
//
//  A README shows a GIF and nothing else: no player, no controls, no file that
//  has to be clicked. So the film is written once as H.264, for anywhere that
//  can play video, and reduced here to the loop that goes in the page.
//
//  Smaller and slower than the film on purpose. A GIF carries every frame as its
//  own image with a palette of 256 colors, so halving the size and taking every
//  fifth frame is the difference between a file a page can load and one it
//  cannot.
//

import AVFoundation
import AppKit
import ImageIO
import UniformTypeIdentifiers

/// How wide the loop is drawn, in pixels, and how many frames it keeps a second.
private let gifWidth = 900
private let gifFramesPerSecond = 12

@main
enum GenerateDemoGIF {
	/// Read the film and write the loop.
	///
	/// - Returns: Nothing. The process ends with a message on standard error when
	///   the arguments are wrong or either file cannot be handled.
	static func main() async {
		guard CommandLine.arguments.count == 3 else {
			FileHandle.standardError.write(Data("Expected a film to read and a loop to write\n".utf8))
			exit(1)
		}
		let film = AVURLAsset(url: URL(fileURLWithPath: CommandLine.arguments[1]))
		let output = URL(fileURLWithPath: CommandLine.arguments[2])

		guard
			let duration = try? await film.load(.duration).seconds,
			let track = try? await film.loadTracks(withMediaType: .video).first,
			let size = try? await track.load(.naturalSize)
		else {
			FileHandle.standardError.write(Data("The film could not be read\n".utf8))
			exit(1)
		}
		let height = Int((Double(gifWidth) * size.height / size.width).rounded())

		let generator = AVAssetImageGenerator(asset: film)
		generator.appliesPreferredTrackTransform = true
		generator.maximumSize = CGSize(width: gifWidth, height: height)
		generator.requestedTimeToleranceBefore = .zero
		generator.requestedTimeToleranceAfter = .zero

		let count = Int(duration * Double(gifFramesPerSecond))
		guard let destination = CGImageDestinationCreateWithURL(
			output as CFURL,
			UTType.gif.identifier as CFString,
			count,
			nil
		) else {
			FileHandle.standardError.write(Data("The loop could not be opened for writing\n".utf8))
			exit(1)
		}
		CGImageDestinationSetProperties(destination, [
			kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFLoopCount: 0],
		] as CFDictionary)

		let frameProperties = [
			kCGImagePropertyGIFDictionary: [
				kCGImagePropertyGIFDelayTime: 1.0 / Double(gifFramesPerSecond),
				kCGImagePropertyGIFUnclampedDelayTime: 1.0 / Double(gifFramesPerSecond),
			],
		] as CFDictionary

		for index in 0..<count {
			let seconds = Double(index) / Double(gifFramesPerSecond)
			guard let frame = try? await generator.image(at: CMTime(seconds: seconds, preferredTimescale: 600)).image else {
				FileHandle.standardError.write(Data("Frame \(index) could not be read\n".utf8))
				exit(1)
			}
			CGImageDestinationAddImage(destination, frame, frameProperties)
		}

		guard CGImageDestinationFinalize(destination) else {
			FileHandle.standardError.write(Data("The loop could not be written\n".utf8))
			exit(1)
		}
	}
}
