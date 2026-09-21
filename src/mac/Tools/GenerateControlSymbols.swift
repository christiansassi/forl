// Generate native symbol assets because Control Center cannot render arbitrary views.

import AppKit
import CoreText

@main
enum GenerateControlSymbols {
	/// Side of the square the gauge is laid out in, before the symbol is scaled.
	static let canvas: CGFloat = 100
	/// Layer the filled part of the dial, the reading and the mark are drawn in.
	static let primaryLayer = "hierarchical-0:primary"
	/// Layer the unfilled part of the dial is drawn in, which the symbol renders
	/// at half strength. It is the one thing in the gauge that is not the color
	/// the rest of it is, and a compiled symbol has no other way to say so.
	static let trackLayer = "hierarchical-0:secondary"
	/// Point size the reading is outlined at, in canvas units.
	static let numberSize: CGFloat = 32
	/// How tall the artwork is compared with the capline to baseline band.
	///
	/// A compiled symbol is scaled so that band matches the cap height of the
	/// surrounding font, so this ratio, not the size of the paths, decides how
	/// large the gauge comes out. A system symbol sits at about 1.4; the gauge
	/// is drawn larger because it carries a number that has to stay readable,
	/// and is set so that it fills a Control Center tile about as much as one
	/// of the system's own round controls does.
	static let frameToCapHeight: CGFloat = 2.7
	/// How far the artwork is lifted off the capline to baseline band, as a share
	/// of its own height.
	///
	/// A symbol is placed by where its ink sits against the baseline, the way a
	/// letter is. Artwork centered on the band hangs a long way under the
	/// baseline once it is this much taller than the band, and Control Center
	/// then draws the gauge low in its tile.
	static let frameLift: CGFloat = 0.03
	/// Distance between the capline and the baseline of the template's medium row.
	static let templateCapHeight: CGFloat = 70
	/// Middle of the capline to baseline band of the template's medium row.
	static let templateCenterY: CGFloat = 311
	/// Top of the margin guides of the template's medium row.
	static let templateMarginTop: CGFloat = 256
	/// Height of the margin guides of the template's medium row.
	static let templateMarginHeight: CGFloat = 110
	/// Where each weight's column sits, horizontally, in the template.
	///
	/// A symbol carries three drawn weights and every other weight and scale is
	/// interpolated between them. The gauge is a fixed drawing that does not
	/// thicken with weight, so all three columns get the same artwork, but all
	/// three have to be there: a symbol that leaves them out compiles without a
	/// complaint and then fails to draw where the system asks for a weight it
	/// cannot derive, which is what Control Center does.
	static let weightColumns: [(name: String, centerX: CGFloat)] = [("Ultralight", 265), ("Regular", 465), ("Black", 665)]
	/// The reference glyph the template carries to show where the type sits.
	static let typeReference = "M85,145.755 L87.685,145.755 L113.369,79.287 L114.052002,79.287 L114.052002,76 L112.148,76 L85,145.755 Z M95.693,121.536 L130.996,121.536 L130.263,119.313 L96.474,119.313 L95.693,121.536 Z M139.14999,145.755 L141.787,145.755 L114.638,76 L113.466,76 L113.466,79.287 L139.14999,145.755 Z"

	/// Serialize a Core Graphics outline into SVG path commands.
	///
	/// - Parameter path: The outline to serialize.
	/// - Returns: The value of an SVG `d` attribute.
	static func svgPath(_ path: CGPath) -> String {
		var commands: [String] = []
		path.applyWithBlock { pointer in
			let element = pointer.pointee
			func point(_ index: Int) -> String {
				let p = element.points[index]
				return String(format: "%.4f %.4f", locale: Locale(identifier: "en_US_POSIX"), p.x, p.y)
			}
			switch element.type {
			case .moveToPoint: commands.append("M\(point(0))")
			case .addLineToPoint: commands.append("L\(point(0))")
			case .addQuadCurveToPoint: commands.append("Q\(point(0)) \(point(1))")
			case .addCurveToPoint: commands.append("C\(point(0)) \(point(1)) \(point(2))")
			case .closeSubpath: commands.append("Z")
			@unknown default: break
			}
		}
		return commands.joined(separator: " ")
	}

	/// Outline the gauge number so the symbol contains no font dependency.
	///
	/// - Parameter text: The reading to draw, such as "42" or "-".
	/// - Returns: The outline, centered in the canvas and wound for SVG's downward y axis.
	static func numberPath(_ text: String) -> CGPath {
		let font = NSFont.monospacedDigitSystemFont(ofSize: numberSize, weight: .semibold)
		let line = CTLineCreateWithAttributedString(NSAttributedString(string: text, attributes: [.font: font]))
		let outline = CGMutablePath()
		for run in CTLineGetGlyphRuns(line) as! [CTRun] {
			let count = CTRunGetGlyphCount(run)
			var glyphs = [CGGlyph](repeating: 0, count: count)
			var positions = [CGPoint](repeating: .zero, count: count)
			CTRunGetGlyphs(run, CFRange(location: 0, length: 0), &glyphs)
			CTRunGetPositions(run, CFRange(location: 0, length: 0), &positions)
			for index in 0..<count {
				if let path = CTFontCreatePathForGlyph(font, glyphs[index], nil) {
					outline.addPath(path, transform: CGAffineTransform(translationX: positions[index].x, y: positions[index].y))
				}
			}
		}
		let bounds = outline.boundingBoxOfPath
		let center = canvas / 2
		var transform = CGAffineTransform(a: 1, b: 0, c: 0, d: -1, tx: center - bounds.midX, ty: center + bounds.midY)
		return outline.copy(using: &transform)!
	}

	/// Outline part of the dial with rounded endpoints.
	///
	/// - Parameters:
	///   - fraction: How much of the 270 degree sweep to draw, from 0 to 1.
	///   - radius: Distance from the center to the middle of the stroke, in canvas units.
	///   - width: Thickness of the stroke, in canvas units.
	/// - Returns: The stroked outline, empty when the fraction is zero.
	static func arc(_ fraction: Double, radius: CGFloat, width: CGFloat) -> CGPath {
		let path = CGMutablePath()
		if fraction > 0 {
			let center = canvas / 2
			path.addArc(center: CGPoint(x: center, y: center), radius: radius, startAngle: DialGeometry.startDegrees * .pi / 180, endAngle: (DialGeometry.startDegrees + DialGeometry.sweepDegrees * fraction) * .pi / 180, clockwise: false)
		}
		return path.copy(strokingWithWidth: width, lineCap: .round, lineJoin: .round, miterLimit: 1)
	}

	/// Read the single outline a provider mark is drawn from.
	///
	/// - Parameter url: Location of the provider's SVG.
	/// - Returns: The value of the SVG's first `d` attribute.
	/// - Throws: An error when the file cannot be read.
	static func markPath(at url: URL) throws -> String {
		let source = try String(contentsOf: url, encoding: .utf8)
		let expression = try NSRegularExpression(pattern: "<path[^>]*\\sd=\"([^\"]+)\"")
		guard let match = expression.firstMatch(in: source, range: NSRange(source.startIndex..., in: source)), let range = Range(match.range(at: 1), in: source) else {
			fatalError("Missing provider path in \(url.lastPathComponent)")
		}
		return String(source[range])
	}

	/// Write every integer reading and the unavailable state as custom symbols.
	///
	/// - Throws: An error when a provider mark cannot be read or the catalog cannot be written.
	static func main() throws {
		guard CommandLine.arguments.count == 3 else { fatalError("Expected macOS source root and output catalog") }
		let root = URL(fileURLWithPath: CommandLine.arguments[1])
		let output = URL(fileURLWithPath: CommandLine.arguments[2])
		let manager = FileManager.default
		try manager.createDirectory(at: output, withIntermediateDirectories: true)
		let catalog = "{\n\t\"info\": {\n\t\t\"author\": \"xcode\",\n\t\t\"version\": 1\n\t}\n}\n"
		try catalog.write(to: output.appendingPathComponent("Contents.json"), atomically: true, encoding: .utf8)

		// The unfilled part of the dial is the whole sweep, drawn under the filled
		// part in the layer the symbol renders at half strength. Drawing the whole
		// sweep also means every reading has the same outline, so the gauge keeps
		// one size instead of growing with the number it shows.
		let stroke = canvas * DialGeometry.stroke
		let radius = canvas * DialGeometry.radius
		let track = arc(1, radius: radius, width: stroke)
		let markSize = canvas * DialGeometry.markSize
		let markOrigin = CGPoint(x: (canvas - markSize) / 2, y: canvas * DialGeometry.markCenterY - markSize / 2)
		let frame = track.boundingBoxOfPath.union(CGRect(origin: markOrigin, size: CGSize(width: markSize, height: markSize)))

		// Fit the artwork to the template's own coordinates: the cap height band
		// decides the size the symbol is drawn at, and the margin guides decide
		// how much room it is given beside the text it sits next to.
		let scale = frameToCapHeight * templateCapHeight / frame.height
		let width = scale * frame.width
		let margins = weightColumns.map {
			let left = $0.centerX - width / 2
			let right = $0.centerX + width / 2
			return "<path id=\"left-margin-\($0.name)-M\" d=\"M\(left),\(templateMarginTop) l0,\(templateMarginHeight)\"/><path id=\"right-margin-\($0.name)-M\" d=\"M\(right),\(templateMarginTop) l0,\(templateMarginHeight)\"/>"
		}.joined()
		let guides = """
		<path id="Capline-S" d="M18,76 l800,0"/><path id="H-reference" d="\(typeReference)"/><path id="Baseline-S" d="M18,146 l800,0"/>\(margins)<path id="Capline-M" d="M18,276 l800,0"/><path id="Baseline-M" d="M18,346 l800,0"/><path id="Capline-L" d="M18,476 l800,0"/><path id="Baseline-L" d="M18,546 l800,0"/>
		"""

		for provider in ["claude", "chatgpt"] {
			let mark = try markPath(at: root.appendingPathComponent("../common/assets/\(provider).svg"))
			for value in -1...100 {
				let label = value < 0 ? "none" : String(value)
				let directory = output.appendingPathComponent("ControlGauge-\(provider)-\(label).symbolset")
				try manager.createDirectory(at: directory, withIntermediateDirectories: true)
				let progress = arc(Double(max(0, value)) / 100, radius: radius, width: stroke)
				let number = numberPath(value < 0 ? "-" : label)
				let filled = progress.isEmpty ? "" : "<path class=\"\(primaryLayer)\" d=\"\(svgPath(progress))\"/>"
				let artwork = "<path class=\"\(trackLayer)\" d=\"\(svgPath(track))\"/>\(filled)<path class=\"\(primaryLayer)\" d=\"\(svgPath(number))\"/><path class=\"\(primaryLayer)\" transform=\"translate(\(markOrigin.x) \(markOrigin.y)) scale(\(markSize / 24))\" d=\"\(mark)\"/>"
				let symbols = weightColumns.map {
					let x = $0.centerX - scale * frame.midX
					let y = templateCenterY - scale * (frame.midY + frame.height * frameLift)
					return "<g id=\"\($0.name)-M\" transform=\"translate(\(x) \(y)) scale(\(scale))\">\(artwork)</g>"
				}.joined()
				let svg = """
				<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">
				<g id="Notes"><text id="template-version">Template v.3.0</text></g>
				<g id="Guides">\(guides)</g>
				<g id="Symbols">\(symbols)</g>
				</svg>
				"""
				try svg.write(to: directory.appendingPathComponent("Gauge.svg"), atomically: true, encoding: .utf8)
				// The rendering intent has to be declared here, not left to the view
				// that draws it: a control's icon is drawn by Control Center, which
				// asks for no mode of its own, and without this the two layers come
				// out the same strength and the dial reads as full at every value.
				let contents = "{\n\t\"info\": {\"author\": \"xcode\", \"version\": 1},\n\t\"properties\": {\"symbol-rendering-intent\": \"hierarchical\"},\n\t\"symbols\": [{\"filename\": \"Gauge.svg\", \"idiom\": \"universal\"}]\n}\n"
				try contents.write(to: directory.appendingPathComponent("Contents.json"), atomically: true, encoding: .utf8)
				let legacy = output.appendingPathComponent("Usage-\(provider)-\(label).symbolset")
				if manager.fileExists(atPath: legacy.path) { try manager.removeItem(at: legacy) }
			}
		}
	}
}
