"""Read Claude usage through the login Claude Code stores on this machine.

Calls the endpoint behind the /usage command with the OAuth token from
~/.claude/.credentials.json, and turns the response into the value objects the
interface renders. The response carries both a set of named windows and a
normalized "limits" array; the array is preferred because it already gives a
percentage and a reset time for every window.
"""

from __future__ import annotations

import re
import time
from typing import Any

from ..usage.errors import CredentialsError
from ..usage.http import fetch_json
from ..usage.snapshot import (
	SESSION_KEY,
	SESSION_LABEL,
	WEEKLY_KEY,
	WEEKLY_LABEL,
	BreakdownRow,
	UsageSnapshot,
	UsageWindow,
	clamp_percent,
	now_utc,
	parse_timestamp,
)
from .local_auth import home_file, read_auth_file

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA_HEADER = "oauth-2025-04-20"
USER_AGENT = "claude-usage-widget/1.0"

CONFIG_ENV_VAR = "CLAUDE_CONFIG_DIR"
CONFIG_DIR = ".claude"
CREDENTIALS_FILE = ".credentials.json"
OAUTH_SECTION = "claudeAiOauth"
SIGN_IN_HINT = "claude auth login"

# Rate limit tiers are named like "default_claude_max_5x", and the multiplier is
# the part of the plan name the user recognizes.
TIER_MULTIPLIER_PATTERN = re.compile(r"_(\d+)x$")

SESSION_KIND = "session"
WEEKLY_ALL_KIND = "weekly_all"
WEEKLY_SCOPED_KIND = "weekly_scoped"

EXPIRY_MARGIN_SECONDS = 60


def _plan_label(section: dict[str, Any]) -> str:
	"""Return the plan as it is named to the user, including the multiplier.

	A Max subscription comes in more than one size, and which one is in force
	decides what every percentage on screen is a percentage of, so the
	multiplier belongs next to the plan name.

	Args:
		section: The OAuth section of the credentials file. dict.

	Returns:
		str: Text such as "Max 5x", or just the plan name when the tier carries
		no multiplier.
	"""
	name = str(section.get("subscriptionType") or "unknown").replace("_", " ").title()
	match = TIER_MULTIPLIER_PATTERN.search(str(section.get("rateLimitTier") or ""))
	return f"{name} {match.group(1)}x" if match else name


def _load_login() -> tuple[str, str]:
	"""Read the access token and plan name Claude Code has stored.

	Returns:
		tuple[str, str]: The bearer token and the plan label.
	"""
	path = home_file(CONFIG_ENV_VAR, CONFIG_DIR, CREDENTIALS_FILE)
	document = read_auth_file(path, SIGN_IN_HINT)

	section = document.get(OAUTH_SECTION)
	if not isinstance(section, dict):
		raise CredentialsError(f"Not signed in. Run '{SIGN_IN_HINT}' to sign in.")
	token = section.get("accessToken")
	if not isinstance(token, str) or not token.strip():
		raise CredentialsError(f"Not signed in. Run '{SIGN_IN_HINT}' to sign in.")

	# expiresAt is written in milliseconds by Claude Code.
	expires_at_ms = section.get("expiresAt")
	if isinstance(expires_at_ms, (int, float)) and expires_at_ms:
		if expires_at_ms / 1000.0 - time.time() < EXPIRY_MARGIN_SECONDS:
			raise CredentialsError(f"Sign-in expired. Run '{SIGN_IN_HINT}' to sign in again.")
	return token, _plan_label(section)


def _scope_name(scope: Any) -> str:
	"""Return the name of the model or surface a scoped limit applies to.

	Args:
		scope: The scope object of a limit entry. Expected dict or None.

	Returns:
		str: The name, or an empty string when the scope carries none.
	"""
	if isinstance(scope, dict):
		for field_name in ("model", "surface"):
			holder = scope.get(field_name)
			if isinstance(holder, dict):
				name = holder.get("display_name")
				if isinstance(name, str) and name.strip():
					return name.strip()
	return ""


def _window_from_limit(entry: dict[str, Any], key: str, label: str, scope_name: str = "") -> UsageWindow:
	"""Build a usage window from one entry of the limits array.

	Args:
		entry: A single limit object from the usage document. dict.
		key: Stable identifier to store on the window. str.
		label: Human readable name to store on the window. str.
		scope_name: Name of the model the limit applies to, empty when it covers
			the whole account. str.

	Returns:
		UsageWindow: The window described by that entry.
	"""
	return UsageWindow(
		key=key,
		label=label,
		percent=clamp_percent(entry.get("percent")),
		resets_at=parse_timestamp(entry.get("resets_at")),
		scope_name=scope_name,
	)


def _window_from_named(section: Any, key: str, label: str) -> UsageWindow | None:
	"""Build a usage window from one of the named top level sections.

	Args:
		section: A section such as five_hour from the usage document. Expected
			dict or None.
		key: Stable identifier to store on the window. str.
		label: Human readable name to store on the window. str.

	Returns:
		UsageWindow or None: The window, or None when the section is absent.
	"""
	if not isinstance(section, dict):
		return None
	return UsageWindow(
		key=key,
		label=label,
		percent=clamp_percent(section.get("utilization")),
		resets_at=parse_timestamp(section.get("resets_at")),
	)


def parse(document: dict[str, Any], plan: str) -> UsageSnapshot:
	"""Build a usage snapshot from a decoded Claude usage response.

	Args:
		document: The decoded JSON body returned by the usage endpoint. dict.
		plan: Plan name from the local sign-in. str.

	Returns:
		UsageSnapshot: The parsed reading. It always carries a session window,
		reading 0 percent when the response reports none.
	"""
	raw_limits = document.get("limits")
	raw_limits = raw_limits if isinstance(raw_limits, list) else []

	session: UsageWindow | None = None
	weekly: UsageWindow | None = None
	scoped: list[UsageWindow] = []
	for entry in raw_limits:
		if not isinstance(entry, dict):
			continue
		kind = entry.get("kind")
		if kind == SESSION_KIND and session is None:
			session = _window_from_limit(entry, SESSION_KEY, SESSION_LABEL)
		elif kind == WEEKLY_ALL_KIND and weekly is None:
			weekly = _window_from_limit(entry, WEEKLY_KEY, WEEKLY_LABEL)
		elif kind == WEEKLY_SCOPED_KIND:
			name = _scope_name(entry.get("scope"))
			label = f"{name} this week" if name else f"Scoped limit {len(scoped) + 1} this week"
			scoped.append(_window_from_limit(entry, f"scoped_{len(scoped)}", label, scope_name=name))

	if session is None:
		session = _window_from_named(document.get("five_hour"), SESSION_KEY, SESSION_LABEL)
	if weekly is None:
		weekly = _window_from_named(document.get("seven_day"), WEEKLY_KEY, WEEKLY_LABEL)
	if session is None:
		session = UsageWindow(key=SESSION_KEY, label=SESSION_LABEL, percent=0.0)

	breakdown: list[BreakdownRow] = []
	breakdown_section = document.get("seven_day_breakdown")
	if isinstance(breakdown_section, dict):
		rows = breakdown_section.get("rows")
		for row in rows if isinstance(rows, list) else []:
			if not isinstance(row, dict):
				continue
			identifier = row.get("key")
			name = row.get("display_name") or identifier
			if isinstance(name, str) and name.strip():
				breakdown.append(
					BreakdownRow(
						key=str(identifier or name),
						label=name,
						percent=clamp_percent(row.get("percent")),
					)
				)

	extra = document.get("extra_usage")
	extra = extra if isinstance(extra, dict) else {}
	enabled = bool(extra.get("is_enabled"))

	return UsageSnapshot(
		fetched_at=now_utc(),
		plan=plan,
		session=session,
		weekly=weekly,
		scoped=tuple(scoped),
		breakdown=tuple(breakdown),
		extra_label="Extra usage" if enabled else "",
		extra_percent=clamp_percent(extra.get("utilization")) if enabled else None,
	)


def read() -> UsageSnapshot:
	"""Take one Claude usage reading.

	Returns:
		UsageSnapshot: The current reading.
	"""
	token, plan = _load_login()
	document = fetch_json(
		USAGE_URL,
		{
			"Authorization": f"Bearer {token}",
			"anthropic-beta": OAUTH_BETA_HEADER,
			"Accept": "application/json",
			"User-Agent": USER_AGENT,
		},
		SIGN_IN_HINT,
	)
	return parse(document, plan)
