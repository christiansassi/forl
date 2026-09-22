//
//  SessionStart.swift
//  When to start a service's five hour session on the user's behalf.
//
//  A five hour window starts with the first message sent in it, so a window that
//  has not started by the time the user sits down starts then, and ends five
//  hours later whatever the user had planned. Sending one short message at a
//  chosen time starts it earlier, so it resets earlier.
//
//  The message is sent once a day, on the days of the week the user picked, at
//  the chosen time or up to a chosen number of minutes after it, which is what
//  lets a machine that was asleep at the time, or a reading that was late, still
//  count. It is sent only while the session reads 0 percent, since a session
//  already running cannot be started again.
//
//  The first message goes out at the first chosen time still to come. Turning
//  the setting on, or moving the time, before today's time has come starts
//  today; after it has gone, tomorrow, so a time already past is never made up
//  for by sending there and then.
//
//  The same rules as the Windows widget, which keeps them in
//  src/windows/schedule/session_start.py. Nothing here reads a clock: the caller
//  passes the time, which keeps every decision testable with a fixed date.
//

import Foundation

/// The schedule of one service's session start, and where it has got to.
struct SessionStart: Codable, Equatable, Sendable {
	/// What is sent. It says nothing, because nobody reads it; any message starts
	/// the window, and a short one costs the least of it.
	static let messageText = "ping"
	/// The spacing of the times and of the grace, in minutes.
	static let minuteStep = 5
	/// The most the grace can be, in minutes.
	static let maxGraceMinutes = 60
	/// How many minutes a day has.
	static let minutesPerDay = 24 * 60
	/// The days of the week, numbered as ISO numbers them: Monday is 1 and
	/// Sunday 7. The Windows widget stores the same numbers.
	static let allWeekdays = [1, 2, 3, 4, 5, 6, 7]

	/// Whether the message is sent at all.
	var enabled = false
	/// When it is sent, as minutes after local midnight, a multiple of the step.
	var minuteOfDay = 8 * 60
	/// How many minutes after that it may still be sent, a multiple of the step.
	var graceMinutes = 5
	/// First day the message may be sent, as a local date: the day the setting
	/// was turned on or its time moved, or the day after when that day's time had
	/// already gone. Nil while it has never been on.
	var startsOn: String?
	/// Day the last message was sent for, so a day gets one message however many
	/// readings fall inside its window.
	var lastSent: String?
	/// The days of the week it runs on, as ISO numbers in order, each once;
	/// empty runs on none.
	var weekdays = allWeekdays

	/// Build the default schedule: off, at 08:00, with five minutes of grace.
	///
	/// - Returns: Nothing.
	init() {}

	/// Read a stored schedule, replacing any field that does not make sense.
	///
	/// Every field is checked rather than trusted, because the file is the
	/// user's; a field that cannot be used is read as its default.
	///
	/// - Parameter decoder: Where the stored schedule is read from.
	/// - Returns: Nothing.
	/// - Throws: Never; an unreadable field falls back to its default.
	init(from decoder: Decoder) throws {
		let container = try? decoder.container(keyedBy: CodingKeys.self)
		let minute = (try? container?.decode(Int.self, forKey: .minuteOfDay)) ?? -1
		let grace = (try? container?.decode(Int.self, forKey: .graceMinutes)) ?? -1
		startsOn = Self.validDay(try? container?.decode(String.self, forKey: .startsOn))
		lastSent = Self.validDay(try? container?.decode(String.self, forKey: .lastSent))
		if (0..<Self.minutesPerDay).contains(minute), minute % Self.minuteStep == 0 {
			minuteOfDay = minute
		}
		if (0...Self.maxGraceMinutes).contains(grace), grace % Self.minuteStep == 0 {
			graceMinutes = grace
		}
		// A list stored empty is kept, since running on no day is a choice; a
		// missing one reads as every day, which is what a schedule stored before
		// there was a choice of days did.
		if let days = try? container?.decode([Int].self, forKey: .weekdays) {
			weekdays = Set(days.filter { (1...7).contains($0) }).sorted()
		}
		// A schedule that is on without a first day would never send, so it is
		// read as off rather than as on and silent.
		enabled = ((try? container?.decode(Bool.self, forKey: .enabled)) ?? false) && startsOn != nil
	}

	/// Return the schedule turned on or off.
	///
	/// - Parameters:
	///   - on: Whether it should now be on.
	///   - now: The moment the change is made.
	/// - Returns: The schedule in the new state. Turning it on sets the first day
	///   to today when the time is still to come and to tomorrow when it has gone;
	///   turning it off keeps the time and the grace, so turning it back on finds
	///   them as they were.
	func switched(_ on: Bool, now: Date) -> SessionStart {
		guard on != enabled else {
			return self
		}
		var next = self
		next.enabled = on
		if on {
			next.startsOn = Self.firstDay(minuteOfDay: minuteOfDay, now: now)
		}
		return next
	}

	/// Return the schedule with its time moved by whole hours or by minute steps.
	///
	/// The hours and the minutes each wrap on their own, as the two fields of a
	/// clock do: stepping the minutes past 55 goes back to 00 without changing
	/// the hour.
	///
	/// - Parameters:
	///   - hours: Hours to add, negative to go back.
	///   - minutes: Minutes to add, negative to go back, a multiple of the step.
	///   - now: The moment the change is made.
	/// - Returns: The schedule at the new time. While it is on, its first day is
	///   worked out again for the new time, as turning it on would.
	func steppedTime(hours: Int, minutes: Int, now: Date) -> SessionStart {
		let hour = minuteOfDay / 60
		let minute = minuteOfDay % 60
		let wrappedHour = ((hour + hours) % 24 + 24) % 24
		let wrappedMinute = ((minute + minutes) % 60 + 60) % 60
		var next = self
		next.minuteOfDay = wrappedHour * 60 + wrappedMinute - wrappedMinute % Self.minuteStep
		if enabled {
			next.startsOn = Self.firstDay(minuteOfDay: next.minuteOfDay, now: now)
		}
		return next
	}

	/// Return the schedule with a new grace.
	///
	/// - Parameter minutes: How late the message may still be sent, snapped to
	///   the step and held between none and the most allowed.
	/// - Returns: The schedule with that grace.
	func withGrace(_ minutes: Int) -> SessionStart {
		var next = self
		let snapped = (minutes / Self.minuteStep) * Self.minuteStep
		next.graceMinutes = min(Self.maxGraceMinutes, max(0, snapped))
		return next
	}

	/// Return the schedule with one day of the week added to it or taken away.
	///
	/// - Parameter weekday: The day, as an ISO number, Monday 1 to Sunday 7.
	/// - Returns: The schedule running on that day when it did not, and not
	///   running on it when it did.
	func toggledWeekday(_ weekday: Int) -> SessionStart {
		var next = self
		next.weekdays = Set(weekdays).symmetricDifference([weekday]).filter { (1...7).contains($0) }.sorted()
		return next
	}

	/// Return the schedule with a day recorded as sent.
	///
	/// - Parameter day: The day the message went out for, as a local date.
	/// - Returns: The schedule, which will not send again for that day.
	func sent(for day: String) -> SessionStart {
		var next = self
		next.lastSent = day
		return next
	}

	/// Return the day a message is due for at a given moment, if one is.
	///
	/// A time late in the evening with a long grace runs past midnight, so the
	/// window that opened yesterday is checked as well as today's.
	///
	/// - Parameter now: The moment to check.
	/// - Returns: The day whose window the moment falls in, which is what to
	///   record as sent, or nil when the schedule is off, has not reached its
	///   first day, does not run on that day of the week, has already sent for
	///   that day, or the moment is outside every window.
	func dueDay(now: Date) -> String? {
		guard enabled, let startsOn else {
			return nil
		}
		let calendar = Calendar.current
		let today = calendar.startOfDay(for: now)
		for back in 0...1 {
			guard let midnight = calendar.date(byAdding: .day, value: -back, to: today) else {
				continue
			}
			let opens = midnight.addingTimeInterval(TimeInterval(minuteOfDay * 60))
			// The grace counts whole minutes, so with 5 minutes 8:05 is still in
			// and with none the chosen minute itself is.
			let closes = opens.addingTimeInterval(TimeInterval((graceMinutes + 1) * 60))
			let day = Self.day(midnight)
			if opens <= now, now < closes, day >= startsOn, day != lastSent, weekdays.contains(Self.isoWeekday(midnight)) {
				return day
			}
		}
		return nil
	}

	/// Return the time as the two fields of a 24 hour clock.
	///
	/// - Returns: The hour and the minute, each two digits, such as ("08", "05").
	func clock() -> (hour: String, minute: String) {
		(String(format: "%02d", minuteOfDay / 60), String(format: "%02d", minuteOfDay % 60))
	}

	/// Return the first day whose chosen time is still to come.
	///
	/// - Parameters:
	///   - minuteOfDay: The chosen time, in minutes after local midnight.
	///   - now: The moment the change is made.
	/// - Returns: Today when the time has not come yet, tomorrow when it has.
	private static func firstDay(minuteOfDay: Int, now: Date) -> String {
		let calendar = Calendar.current
		let today = calendar.startOfDay(for: now)
		let opens = today.addingTimeInterval(TimeInterval(minuteOfDay * 60))
		guard now >= opens, let tomorrow = calendar.date(byAdding: .day, value: 1, to: today) else {
			return day(today)
		}
		return day(tomorrow)
	}

	/// Return a moment as the local date it falls on.
	///
	/// Kept as text in the order year, month, day, so two dates compare the way
	/// the days they name do.
	///
	/// - Parameter date: The moment.
	/// - Returns: The date, such as "2026-09-22".
	static func day(_ date: Date) -> String {
		let parts = Calendar.current.dateComponents([.year, .month, .day], from: date)
		return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
	}

	/// Return the day of the week a moment falls on.
	///
	/// - Parameter date: The moment.
	/// - Returns: The day as an ISO number, Monday 1 to Sunday 7.
	static func isoWeekday(_ date: Date) -> Int {
		// The calendar counts from Sunday as 1; ISO counts from Monday.
		(Calendar.current.component(.weekday, from: date) + 5) % 7 + 1
	}

	/// Return a stored date when it has the shape of one.
	///
	/// - Parameter text: What was stored, or nil.
	/// - Returns: The date, or nil when it is missing or not a date.
	private static func validDay(_ text: String?) -> String? {
		guard let text, text.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) != nil else {
			return nil
		}
		return text
	}
}
