"""The value objects the interface renders.

Nothing here knows which provider a reading came from. A provider turns its own
response shape into these objects, and the tray icons and the panel read only
these, which is what lets one interface serve both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..validation import require_non_empty_str

SESSION_KEY = "session"
WEEKLY_KEY = "weekly"
SESSION_LABEL = "Current session"
WEEKLY_LABEL = "This week"
PRODUCT_KEY_PREFIX = "product:"

LIMIT_GROUP = "limit"
PRODUCT_GROUP = "product"


@dataclass(frozen=True)
class UsageWindow:
	"""One rate limit window and how much of it has been consumed.

	Attributes:
		key: Stable identifier of the window, for example "session". str.
		label: Human readable name shown in the interface. str.
		percent: Share of the window already used, from 0 to 100. float.
		resets_at: Moment the window resets, or None when the provider omits it.
			datetime in UTC or None.
		scope_name: Name of the model the window is limited to, empty for a
			window that covers the whole account. str.
	"""

	key: str
	label: str
	percent: float
	resets_at: datetime | None = None
	scope_name: str = ""


@dataclass(frozen=True)
class BreakdownRow:
	"""A share of the weekly window attributed to one product.

	Attributes:
		key: Stable identifier of the product, for example "claude_code". str.
		label: Product name, for example "Claude Code". str.
		percent: Share of the weekly window used by that product, 0 to 100. float.
	"""

	key: str
	label: str
	percent: float


@dataclass(frozen=True)
class Metric:
	"""One number the user can choose to display in the notification area.

	Limits and products are different things in a response but the same thing to
	the user, so both are offered through this one shape.

	Attributes:
		key: Stable identifier, unique across limits and products. str.
		label: Name shown in the menu and in the panel. str.
		percent: Share already used, from 0 to 100. float.
		resets_at: Moment the underlying window resets, or None. datetime in UTC
			or None.
		group: Either "limit" or "product". str.
	"""

	key: str
	label: str
	percent: float
	resets_at: datetime | None
	group: str


@dataclass(frozen=True)
class UsageSnapshot:
	"""A complete usage reading taken at one moment.

	Attributes:
		fetched_at: When the widget received this reading. datetime in UTC.
		plan: Subscription name to show beside the provider name. str.
		session: The session window, which the icon shows unless the user picks
			another one. UsageWindow.
		weekly: The weekly account window, or None when absent. UsageWindow or None.
		scoped: Per model weekly windows. tuple of UsageWindow.
		breakdown: Weekly usage split by product. tuple of BreakdownRow.
		extra_label: Heading for the extra usage section, empty when the provider
			reports no such budget. str.
		extra_percent: Share of that budget spent, or None when there is none.
			float or None.
	"""

	fetched_at: datetime
	plan: str
	session: UsageWindow
	weekly: UsageWindow | None = None
	scoped: tuple[UsageWindow, ...] = field(default_factory=tuple)
	breakdown: tuple[BreakdownRow, ...] = field(default_factory=tuple)
	extra_label: str = ""
	extra_percent: float | None = None

	def windows(self) -> tuple[UsageWindow, ...]:
		"""Return every limit window, in the order they are offered to the user.

		Returns:
			tuple of UsageWindow: The session window first, then the weekly
			window when present, then any per model window.
		"""
		ordered = [self.session]
		if self.weekly is not None:
			ordered.append(self.weekly)
		ordered.extend(self.scoped)
		return tuple(ordered)

	def metrics(self) -> tuple[Metric, ...]:
		"""Return everything the user can choose to display, limits then products.

		Products are shares of the weekly window, so they inherit that window's
		reset time.

		Returns:
			tuple of Metric: The limit windows in menu order, then one entry per
			product of the weekly breakdown.
		"""
		weekly_reset = self.weekly.resets_at if self.weekly is not None else None
		entries = [
			Metric(
				key=window.key,
				label=window.label,
				percent=window.percent,
				resets_at=window.resets_at,
				group=LIMIT_GROUP,
			)
			for window in self.windows()
		]
		entries.extend(
			Metric(
				key=f"{PRODUCT_KEY_PREFIX}{row.key}",
				label=row.label,
				percent=row.percent,
				resets_at=weekly_reset,
				group=PRODUCT_GROUP,
			)
			for row in self.breakdown
		)
		return tuple(entries)

	def metric(self, key: str) -> Metric | None:
		"""Return one displayable metric by key.

		Args:
			key: The key of the wanted metric, such as "session" or
				"product:claude_code". str, non-empty.

		Returns:
			Metric or None: The matching metric, or None when this reading no
			longer reports it, which happens when a scoped limit empties.
		"""
		require_non_empty_str(key, "key")
		for candidate in self.metrics():
			if candidate.key == key:
				return candidate
		return None


def clamp_percent(value: Any) -> float:
	"""Return a usage percentage clamped into the 0 to 100 range.

	Values outside the range are clamped rather than rejected because a provider
	may report slight overshoot once a limit is exceeded.

	Args:
		value: Percentage reported by a provider. Expected int or float;
			anything else yields 0.0.

	Returns:
		float: The percentage, between 0 and 100 inclusive.
	"""
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return 0.0
	return max(0.0, min(100.0, float(value)))


def parse_timestamp(value: Any) -> datetime | None:
	"""Return an ISO 8601 timestamp from a provider as an aware UTC datetime.

	Args:
		value: Timestamp text such as "2026-09-16T12:00:00+00:00". Expected str;
			anything else yields None.

	Returns:
		datetime or None: The parsed moment in UTC, or None when unparsable.
	"""
	if not isinstance(value, str) or not value:
		return None
	try:
		parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
	except ValueError:
		return None
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
	return parsed.astimezone(timezone.utc)


def parse_epoch(value: Any) -> datetime | None:
	"""Return a Unix timestamp from a provider as an aware UTC datetime.

	Args:
		value: Seconds since the epoch. Expected int or float; anything else
			yields None.

	Returns:
		datetime or None: The parsed moment in UTC, or None when unusable.
	"""
	if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
		return None
	return datetime.fromtimestamp(float(value), tz=timezone.utc)


def now_utc() -> datetime:
	"""Return the current moment in UTC.

	Returns:
		datetime: The current time, timezone aware.
	"""
	return datetime.now(timezone.utc)
