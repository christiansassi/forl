"""When to start a service's five hour session on the user's behalf.

A five hour window starts with the first message sent in it, so a window that
has not started by the time the user sits down starts then, and ends five hours
later whatever the user had planned. Sending one short message at a chosen time
starts it earlier, so it resets earlier.

The message is sent once a day, on the days of the week the user picked, at the
chosen time or up to a chosen number of minutes after it, which is what lets a machine that was asleep at the time, or a
reading that was late, still count. It is sent only while the session reads 0
percent, since a session already running cannot be started again.

The first message goes out at the first chosen time still to come. Turning the
setting on, or moving the time, before today's time has come starts today;
after it has gone, tomorrow, so a time already past is never made up for by
sending there and then.

Nothing here reads a clock or a file. The caller passes the time and stores the
schedule, which keeps every decision testable with a fixed date.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Any

from ..validation import require_int_in_range, require_type

# What is sent. It says nothing, because nobody reads it; any message starts the
# window, and a short one costs the least of it.
MESSAGE_TEXT = "ping"

MINUTES_PER_DAY = 24 * 60
MINUTE_STEP = 5
MAX_GRACE_MINUTES = 60

DEFAULT_MINUTE_OF_DAY = 8 * 60
DEFAULT_GRACE_MINUTES = 5

ENABLED_FIELD = "enabled"
MINUTE_FIELD = "minute_of_day"
GRACE_FIELD = "grace_minutes"
STARTS_ON_FIELD = "starts_on"
LAST_SENT_FIELD = "last_sent"
WEEKDAYS_FIELD = "weekdays"

# The days of the week, numbered as ISO numbers them: Monday is 1 and Sunday 7.
ALL_WEEKDAYS = (1, 2, 3, 4, 5, 6, 7)


@dataclass(frozen=True)
class SessionStart:
	"""The schedule of one service's session start, and where it has got to.

	Attributes:
		enabled: Whether the message is sent at all. bool.
		minute_of_day: When it is sent, as minutes after local midnight. int, 0
			to 1435, a multiple of MINUTE_STEP.
		grace_minutes: How many minutes after that it may still be sent. int, 0
			to MAX_GRACE_MINUTES, a multiple of MINUTE_STEP.
		starts_on: First day the message may be sent: the day the setting was
			turned on or its time moved, or the day after when that day's time
			had already gone. date or None while it has never been on.
		last_sent: Day the last message was sent for, so a day gets one message
			however many readings fall inside its window. date or None.
		weekdays: The days of the week it runs on, as ISO numbers, Monday 1 to
			Sunday 7, in order and each once. tuple of int; empty runs on none.
	"""

	enabled: bool = False
	minute_of_day: int = DEFAULT_MINUTE_OF_DAY
	grace_minutes: int = DEFAULT_GRACE_MINUTES
	starts_on: date | None = None
	last_sent: date | None = None
	weekdays: tuple[int, ...] = ALL_WEEKDAYS

	def __post_init__(self) -> None:
		"""Check every field, so a schedule that exists is one that can be acted on.

		Returns:
			None.
		"""
		require_type(self.enabled, bool, "enabled")
		require_int_in_range(self.minute_of_day, 0, MINUTES_PER_DAY - MINUTE_STEP, "minute_of_day")
		if self.minute_of_day % MINUTE_STEP:
			raise ValueError(f"minute_of_day must be a multiple of {MINUTE_STEP}, got {self.minute_of_day}")
		require_int_in_range(self.grace_minutes, 0, MAX_GRACE_MINUTES, "grace_minutes")
		if self.grace_minutes % MINUTE_STEP:
			raise ValueError(f"grace_minutes must be a multiple of {MINUTE_STEP}, got {self.grace_minutes}")
		for name, value in (("starts_on", self.starts_on), ("last_sent", self.last_sent)):
			if value is not None:
				require_type(value, date, name)
		require_type(self.weekdays, tuple, "weekdays")
		for weekday in self.weekdays:
			require_int_in_range(weekday, 1, 7, "weekdays")
		if list(self.weekdays) != sorted(set(self.weekdays)):
			raise ValueError(f"weekdays must be in order and each once, got {self.weekdays}")


def _first_day(minute_of_day: int, now: datetime) -> date:
	"""Return the first day whose chosen time is still to come.

	Args:
		minute_of_day: The chosen time, in minutes after local midnight. int.
		now: The current local time, without a time zone. datetime.

	Returns:
		date: Today when the time has not come yet, tomorrow when it has.
	"""
	today = now.date()
	opens = datetime.combine(today, datetime.min.time()) + timedelta(minutes=minute_of_day)
	return today if now < opens else today + timedelta(days=1)


def switched(schedule: SessionStart, enabled: bool, now: datetime) -> SessionStart:
	"""Return a schedule turned on or off.

	Args:
		schedule: The schedule as it stands. SessionStart.
		enabled: Whether it should now be on. bool.
		now: The local time the change is made at, without a time zone.
			datetime.

	Returns:
		SessionStart: The schedule with the new state. Turning it on sets the
		first day to today when the time is still to come and to tomorrow when
		it has gone; turning it off keeps the time and the grace, so turning it
		back on finds them as they were.
	"""
	require_type(schedule, SessionStart, "schedule")
	require_type(enabled, bool, "enabled")
	require_type(now, datetime, "now")
	if enabled == schedule.enabled:
		return schedule
	if enabled:
		return replace(schedule, enabled=True, starts_on=_first_day(schedule.minute_of_day, now))
	return replace(schedule, enabled=False)


def stepped_time(schedule: SessionStart, hours: int, minutes: int, now: datetime) -> SessionStart:
	"""Return a schedule with its time moved by whole hours or by minute steps.

	The hours and the minutes each wrap on their own, as the two fields of a
	clock do: stepping the minutes past 55 goes back to 00 without changing the
	hour.

	Args:
		schedule: The schedule as it stands. SessionStart.
		hours: Hours to add, negative to go back. int, -23 to 23.
		minutes: Minutes to add, negative to go back. int, a multiple of
			MINUTE_STEP, -55 to 55.
		now: The local time the change is made at, without a time zone.
			datetime.

	Returns:
		SessionStart: The schedule at the new time. While it is on, its first
		day is worked out again for the new time, as turning it on would.
	"""
	require_type(schedule, SessionStart, "schedule")
	require_int_in_range(hours, -23, 23, "hours")
	require_int_in_range(minutes, -(60 - MINUTE_STEP), 60 - MINUTE_STEP, "minutes")
	if minutes % MINUTE_STEP:
		raise ValueError(f"minutes must be a multiple of {MINUTE_STEP}, got {minutes}")
	require_type(now, datetime, "now")
	hour, minute = divmod(schedule.minute_of_day, 60)
	minute_of_day = ((hour + hours) % 24) * 60 + (minute + minutes) % 60
	if not schedule.enabled:
		return replace(schedule, minute_of_day=minute_of_day)
	return replace(schedule, minute_of_day=minute_of_day, starts_on=_first_day(minute_of_day, now))


def toggled_weekday(schedule: SessionStart, weekday: int) -> SessionStart:
	"""Return a schedule with one day of the week added to it or taken away.

	Args:
		schedule: The schedule as it stands. SessionStart.
		weekday: The day, as an ISO number, Monday 1 to Sunday 7. int.

	Returns:
		SessionStart: The schedule running on that day when it did not, and not
		running on it when it did.
	"""
	require_type(schedule, SessionStart, "schedule")
	require_int_in_range(weekday, 1, 7, "weekday")
	days = set(schedule.weekdays) ^ {weekday}
	return replace(schedule, weekdays=tuple(sorted(days)))


def due_day(schedule: SessionStart, now: datetime) -> date | None:
	"""Return the day a message is due for at a given moment, if one is.

	A time late in the evening with a long grace runs past midnight, so the
	window that opened yesterday is checked as well as today's.

	Args:
		schedule: The schedule. SessionStart.
		now: The current local time, without a time zone. datetime.

	Returns:
		date or None: The day whose window the moment falls in, which is what to
		record as sent. None when the schedule is off, has not reached its first
		day, does not run on that day of the week, has already sent for that day,
		or the moment is outside every window.
	"""
	require_type(schedule, SessionStart, "schedule")
	require_type(now, datetime, "now")
	if not schedule.enabled or schedule.starts_on is None:
		return None
	for day in (now.date(), now.date() - timedelta(days=1)):
		opens = datetime.combine(day, datetime.min.time()) + timedelta(minutes=schedule.minute_of_day)
		# The grace counts whole minutes, so with 5 minutes 8:05 is still in and
		# with none the chosen minute itself is.
		closes = opens + timedelta(minutes=schedule.grace_minutes + 1)
		if (
			opens <= now < closes
			and day >= schedule.starts_on
			and day != schedule.last_sent
			and day.isoweekday() in schedule.weekdays
		):
			return day
	return None


def to_dict(schedule: SessionStart) -> dict[str, Any]:
	"""Return a schedule as plain values for the preferences file.

	Args:
		schedule: The schedule. SessionStart.

	Returns:
		dict[str, Any]: The fields, with the dates as ISO strings or None.
	"""
	require_type(schedule, SessionStart, "schedule")
	return {
		ENABLED_FIELD: schedule.enabled,
		MINUTE_FIELD: schedule.minute_of_day,
		GRACE_FIELD: schedule.grace_minutes,
		STARTS_ON_FIELD: schedule.starts_on.isoformat() if schedule.starts_on else None,
		LAST_SENT_FIELD: schedule.last_sent.isoformat() if schedule.last_sent else None,
		WEEKDAYS_FIELD: list(schedule.weekdays),
	}


def _date_field(section: dict[str, Any], field: str) -> date | None:
	"""Return one stored date, or None when it is missing or unusable.

	Args:
		section: The stored schedule. dict.
		field: Name of the field. str.

	Returns:
		date or None: The date.
	"""
	value = section.get(field)
	if not isinstance(value, str):
		return None
	try:
		return date.fromisoformat(value)
	except ValueError:
		return None


def from_dict(section: Any) -> SessionStart:
	"""Return the schedule stored in the preferences file.

	Every field is checked rather than trusted, because the file is editable by
	hand; a field that does not make sense is replaced by its default.

	Args:
		section: What the file holds for the schedule. Any; anything but a dict
			gives the default schedule.

	Returns:
		SessionStart: The stored schedule.
	"""
	if not isinstance(section, dict):
		return SessionStart()
	enabled = section.get(ENABLED_FIELD)
	minute = section.get(MINUTE_FIELD)
	grace = section.get(GRACE_FIELD)
	minute_ok = (
		isinstance(minute, int)
		and not isinstance(minute, bool)
		and 0 <= minute < MINUTES_PER_DAY
		and minute % MINUTE_STEP == 0
	)
	grace_ok = (
		isinstance(grace, int)
		and not isinstance(grace, bool)
		and 0 <= grace <= MAX_GRACE_MINUTES
		and grace % MINUTE_STEP == 0
	)
	starts_on = _date_field(section, STARTS_ON_FIELD)
	return SessionStart(
		# A schedule that is on without a first day would never send, so it is
		# read as off rather than as on and silent.
		enabled=enabled is True and starts_on is not None,
		minute_of_day=minute if minute_ok else DEFAULT_MINUTE_OF_DAY,
		grace_minutes=grace if grace_ok else DEFAULT_GRACE_MINUTES,
		starts_on=starts_on,
		last_sent=_date_field(section, LAST_SENT_FIELD),
		weekdays=_weekdays_field(section),
	)


def _weekdays_field(section: dict[str, Any]) -> tuple[int, ...]:
	"""Return the stored days of the week, or every day when none were stored.

	A list that was stored empty is kept empty, since running on no day is a
	choice; a missing or unusable one reads as every day, which is what a
	schedule stored before there was a choice of days did.

	Args:
		section: The stored schedule. dict.

	Returns:
		tuple[int, ...]: The days as ISO numbers, in order and each once.
	"""
	value = section.get(WEEKDAYS_FIELD)
	if not isinstance(value, list):
		return ALL_WEEKDAYS
	days = {day for day in value if isinstance(day, int) and not isinstance(day, bool) and 1 <= day <= 7}
	return tuple(sorted(days))


def format_time(minute_of_day: int) -> tuple[str, str]:
	"""Return a time of day as the two fields of a 24 hour clock.

	Args:
		minute_of_day: Minutes after midnight. int, 0 to 1439.

	Returns:
		tuple[str, str]: The hour and the minute, each two digits, such as
		("08", "05").
	"""
	require_int_in_range(minute_of_day, 0, MINUTES_PER_DAY - 1, "minute_of_day")
	hour, minute = divmod(minute_of_day, 60)
	return (f"{hour:02d}", f"{minute:02d}")
