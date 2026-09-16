"""Convert usage values into the strings shown in the interface.

The wording follows Claude's own usage view: a window is named "Current session"
or "This week" and is described by when it resets, as a wall clock time rather
than a countdown. Both the icon tooltip and the panel describe the same numbers,
so that wording lives here once instead of being written twice.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..usage.snapshot import UsageWindow
from ..validation import require_number_in_range, require_type


def format_percent(percent: float) -> str:
	"""Return a usage percentage as a whole number followed by a percent sign.

	Args:
		percent: Share of a window already used, 0 to 100. float.

	Returns:
		str: Text such as "24%".
	"""
	require_number_in_range(percent, 0.0, 100.0, "percent")
	return f"{int(round(percent))}%"


def local_minute(moment: datetime) -> datetime:
	"""Return a moment in local time, rounded to the nearest minute.

	Reset times arrive one second short of the hour, so rounding is what turns
	"Saturday 11:59:59 PM" into the "Sunday 12:00 AM" a reader expects.

	Args:
		moment: The moment to convert. datetime, aware or naive UTC.

	Returns:
		datetime: The same moment in the local time zone, with seconds dropped.
	"""
	require_type(moment, datetime, "moment")
	aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
	local = aware.astimezone()
	rounded = local.replace(second=0, microsecond=0)
	return rounded + timedelta(minutes=1) if local.second >= 30 else rounded


def format_clock(moment: datetime) -> str:
	"""Return the local wall clock time of a moment, on a twelve hour clock.

	Args:
		moment: The moment to render. datetime, aware or naive UTC.

	Returns:
		str: Text such as "2:00 PM".
	"""
	local = local_minute(moment)
	return f"{local.hour % 12 or 12}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


def format_reset_at(resets_at: datetime | None, now: datetime | None = None) -> str:
	"""Return a sentence saying when a window resets.

	The day is named only when the reset is not today, which is how Claude's own
	usage view reads.

	Args:
		resets_at: Moment the window resets, or None when none was reported.
			datetime or None.
		now: Reference moment, or None for the current time. datetime or None.

	Returns:
		str: Text such as "Resets at 2:00 PM" or "Resets Sunday 12:00 AM", and an
		empty string when there is no reset time.
	"""
	if resets_at is None:
		return ""
	require_type(resets_at, datetime, "resets_at")
	if now is not None:
		require_type(now, datetime, "now")

	reference = (now or datetime.now(timezone.utc)).astimezone()
	local = local_minute(resets_at)
	if local.date() == reference.date():
		return f"Resets at {format_clock(resets_at)}"
	return f"Resets {local.strftime('%A')} {format_clock(resets_at)}"


def format_reset(window: UsageWindow, now: datetime | None = None) -> str:
	"""Return a sentence saying when a usage window resets.

	Args:
		window: The window to describe. UsageWindow.
		now: Reference moment, or None for the current time. datetime or None.

	Returns:
		str: Text such as "Resets at 2:00 PM", and an empty string when the
		endpoint reported no reset time.
	"""
	require_type(window, UsageWindow, "window")
	return format_reset_at(window.resets_at, now)


def format_subtitle(window: UsageWindow, now: datetime | None = None) -> str:
	"""Return the second line shown under a window name.

	Args:
		window: The window to describe. UsageWindow.
		now: Reference moment, or None for the current time. datetime or None.

	Returns:
		str: The reset sentence, preceded on its own line for a per model window
		by what that limit covers.
	"""
	require_type(window, UsageWindow, "window")
	reset = format_reset(window, now)
	if not window.scope_name:
		return reset
	scope = f"Separate weekly limit for {window.scope_name}"
	return f"{scope}\n{reset}" if reset else scope


def format_next_update(seconds: float) -> str:
	"""Return the line saying how long until the next reading.

	Args:
		seconds: Time remaining until the next reading. float, negative values
			read as zero.

	Returns:
		str: Text such as "Next update in 42s".
	"""
	require_type(seconds, (int, float), "seconds")
	return f"Next update in {max(0, int(seconds))}s"
