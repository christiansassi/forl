//
//  Formatting.swift
//  Turn usage values into the strings every surface shows.
//
//  The wording follows Claude's own usage view: a window is named "Current
//  session" or "This week" and is described by when it resets, as a wall clock
//  time rather than a countdown. Every surface describes the same numbers, so
//  the wording lives here once.
//

import Foundation

/// The strings a reading is written as.
enum Formatting {
	/// Return a usage percentage as a whole number followed by a percent sign.
	///
	/// - Parameter percent: Share of a window already used, 0 to 100.
	/// - Returns: Text such as "24%".
	static func percent(_ percent: Double) -> String {
		"\(Int(clampPercent(percent).rounded()))%"
	}

	/// Return the hover text for one small surface.
	///
	/// The reading comes first, because how much is left is the question a hover
	/// asks, and the name follows it, because several items may be up at once
	/// and a number alone does not say which limit it belongs to.
	///
	/// - Parameters:
	///   - value: Share of the window already used, 0 to 100.
	///   - label: Name of the window, such as "Current session".
	///   - resetsAt: Reset time for the reading, or nil when unavailable.
	/// - Returns: The percentage and window name, followed by the reset time when known.
	static func tooltip(value: Double, label: String, resetsAt: Date? = nil) -> String {
		let resetText = reset(resetsAt)
		let title = "\(percent(value)) - \(label)"
		return resetText.isEmpty ? title : "\(title) - \(resetText)"
	}

	/// Return the local wall clock time of a moment, on a twelve hour clock.
	///
	/// - Parameter moment: The moment to render.
	/// - Returns: Text such as "2:00 PM".
	static func clock(_ moment: Date) -> String {
		let formatter = DateFormatter()
		formatter.locale = Locale(identifier: "en_US_POSIX")
		formatter.dateFormat = "h:mm a"
		return formatter.string(from: rounded(moment))
	}

	/// Return a sentence saying when a window resets.
	///
	/// The day is named only when the reset is not today, which is how Claude's
	/// own usage view reads.
	///
	/// - Parameters:
	///   - resetsAt: Moment the window resets, or nil when none was reported.
	///   - now: Reference moment, for deciding whether the reset is today.
	/// - Returns: Text such as "Resets at 2:00 PM" or "Resets Sunday 12:00 AM",
	///   and an empty string when there is no reset time.
	static func reset(_ resetsAt: Date?, now: Date = Date()) -> String {
		guard let resetsAt else {
			return ""
		}
		let moment = rounded(resetsAt)
		if Calendar.current.isDate(moment, inSameDayAs: now) {
			return "Resets at \(clock(resetsAt))"
		}
		let day = DateFormatter()
		day.locale = Locale(identifier: "en_US_POSIX")
		day.dateFormat = "EEEE"
		return "Resets \(day.string(from: moment)) \(clock(resetsAt))"
	}

	/// Return the lines set under a window's name.
	///
	/// - Parameters:
	///   - metric: The metric to describe.
	///   - now: Reference moment, for deciding whether the reset is today.
	/// - Returns: The reset sentence, preceded for a per model window by what
	///   that limit covers.
	static func subtitle(_ metric: Metric, now: Date = Date()) -> String {
		let resets = reset(metric.resetsAt, now: now)
		guard !metric.scopeName.isEmpty else {
			return resets
		}
		let scope = "Separate weekly limit for \(metric.scopeName)"
		return resets.isEmpty ? scope : "\(scope)\n\(resets)"
	}

	/// Return the line saying how long until the next reading.
	///
	/// - Parameter seconds: Time remaining until the next reading.
	/// - Returns: Text such as "Next update in 42s".
	static func nextUpdate(in seconds: TimeInterval) -> String {
		"Next update in \(Int(max(0, seconds)))s"
	}

	/// Return a moment rounded to the nearest minute.
	///
	/// Reset times arrive one second short of the hour, so rounding is what
	/// turns "Saturday 11:59:59 PM" into the "Sunday 12:00 AM" a reader expects.
	///
	/// - Parameter moment: The moment to round.
	/// - Returns: The same moment with its seconds dropped or carried.
	private static func rounded(_ moment: Date) -> Date {
		Date(timeIntervalSinceReferenceDate: (moment.timeIntervalSinceReferenceDate / 60).rounded() * 60)
	}
}
