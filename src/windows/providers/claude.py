"""Read Claude usage with the sign-in the widget made for itself.

Calls the endpoint behind the /usage command with a token this widget obtained
in the browser and keeps in its own file, renewing it when it is close to
running out, and turns the response into the value objects the interface
renders. The response carries both a set of named windows and a normalized
"limits" array; the array is preferred because it already gives a percentage and
a reset time for every window.

It names no plan, so the plan shown beside the product name comes from the
account endpoint, asked alongside every reading. That is one small extra request
a minute and it is what lets an upgrade show up without signing in again.

Starting a session is one message to the smallest model, asking for a single
token back, which is as little of the session as a message can use.
"""

from __future__ import annotations

import re
from typing import Any, Callable, NamedTuple

from ..auth import oauth, store
from ..auth.oauth import OAuthClient
from ..usage.errors import CredentialsError, UsageRequestError
from ..schedule.session_start import MESSAGE_TEXT
from ..usage.http import fetch_json, post_json
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

KEY = "claude"
LABEL = "Claude"

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"
MESSAGES_URL = "https://api.anthropic.com/v1/messages"
OAUTH_BETA_HEADER = "oauth-2025-04-20"
API_VERSION = "2023-06-01"
# The smallest model, which is also the one a sign-in of this kind may send to
# without presenting itself as the tool the sign-in was made for.
SESSION_START_MODEL = "claude-haiku-4-5"
USER_AGENT = "claude-usage-widget/1.0"

# What the browser is sent to, and where a code or a refresh token is
# exchanged. The exchange is on the API host, which answers a plain client;
# the pages that serve the authorization form sit behind a bot check and are
# for the browser only.
#
# Two scopes, which are what the usage and account endpoints need and no more.
# The tool these endpoints were built for also asks for the scope that mints API
# keys, for file upload, for MCP servers and for plugins; a widget that reads
# one number has no business holding any of those. Asking for that whole set was
# tried and refused, and the sign-in it does issue grants no API key scope
# either, so the wide request appears to be the thing the page objects to.
OAUTH = OAuthClient(
	key=KEY,
	label=LABEL,
	authorize_url="https://claude.com/cai/oauth/authorize",
	token_url="https://api.anthropic.com/v1/oauth/token",
	# Public identifier of the application these endpoints were built for. A
	# client that runs on the user's machine can hold no secret, which is what
	# the proof key in the flow is for.
	client_id="9d1c250a-e61b-44d9-88ed-5944d1962f5e",
	scope="user:profile user:inference",
	# Any free loopback port is accepted, so one is asked for rather than
	# chosen: a fixed port is a port that can already be taken.
	redirect_port=0,
	redirect_path="/callback",
	# The authorization page hands back a code rather than a token.
	authorize_extras=(("code", "true"),),
	headers=(("User-Agent", USER_AGENT),),
)

# Rate limit tiers are named like "default_claude_max_5x": the plan, and for
# Max the multiplier, which is what decides what every percentage on screen is
# a percentage of and so belongs next to the plan name.
TIER_PATTERN = re.compile(r"^default_claude_(?P<name>[a-z_]+?)(?:_(?P<multiplier>\d+)x)?$")
UNKNOWN_PLAN = "Unknown"

SESSION_KIND = "session"
WEEKLY_ALL_KIND = "weekly_all"
WEEKLY_SCOPED_KIND = "weekly_scoped"


class Login(NamedTuple):
	"""What the stored Claude sign-in yields.

	Attributes:
		token: Bearer token accepted by the usage endpoint. str.
		plan: Plan name as it is shown to the user, such as "Max 5x". str.
	"""

	token: str
	plan: str


def _headers(token: str) -> dict[str, str]:
	"""Return the headers every authenticated Claude request carries.

	Args:
		token: The bearer token to send. str, non-empty.

	Returns:
		dict[str, str]: The headers, ready to pass to the transport.
	"""
	return {
		"Authorization": f"Bearer {token}",
		"anthropic-beta": OAUTH_BETA_HEADER,
		"Accept": "application/json",
		"User-Agent": USER_AGENT,
	}


def _section(document: dict[str, Any], name: str) -> dict[str, Any]:
	"""Return one named object of a response, or an empty one.

	Args:
		document: The decoded response. dict.
		name: Name of the object to take, such as "account". str, non-empty.

	Returns:
		dict[str, Any]: The object, empty when it is missing or not an object.
	"""
	section = document.get(name)
	return section if isinstance(section, dict) else {}


def _plan_label(profile: dict[str, Any]) -> str:
	"""Return the plan as it is named to the user, including the multiplier.

	A Max subscription comes in more than one size, and which one is in force
	decides what every percentage on screen is a percentage of, so the
	multiplier belongs next to the plan name. The rate limit tier names both;
	the flags on the account are read only when it names neither.

	Args:
		profile: The decoded account endpoint response. dict.

	Returns:
		str: Text such as "Max 5x", or "Pro", or "Unknown" when nothing in the
		response says.
	"""
	match = TIER_PATTERN.match(str(_section(profile, "organization").get("rate_limit_tier") or ""))
	if match:
		name = match.group("name").replace("_", " ").title()
		multiplier = match.group("multiplier")
		return f"{name} {multiplier}x" if multiplier else name

	account = _section(profile, "account")
	if account.get("has_claude_max"):
		return "Max"
	if account.get("has_claude_pro"):
		return "Pro"
	return UNKNOWN_PLAN


def _account_name(profile: dict[str, Any]) -> str:
	"""Return who is signed in, as the settings should name them.

	Args:
		profile: The decoded account endpoint response. dict.

	Returns:
		str: The email address, falling back to whichever name the response
		carries, or an empty string when it carries none.
	"""
	account = _section(profile, "account")
	for field in ("email", "display_name", "full_name"):
		value = account.get(field)
		if isinstance(value, str) and value.strip():
			return value.strip()
	return ""


def _profile(token: str) -> dict[str, Any]:
	"""Return what the account endpoint says about the signed-in account.

	Args:
		token: The bearer token to ask with. str, non-empty.

	Returns:
		dict[str, Any]: The decoded response, empty when it could not be had.
		Losing it costs the plan name beside the product; treating that as a
		failed reading would cost the reading itself.
	"""
	try:
		return fetch_json(PROFILE_URL, _headers(token))
	except UsageRequestError:
		return {}


def sign_in(on_address: Callable[[str, bool], None]) -> str:
	"""Sign in to Claude in the browser and store what comes back.

	Blocks until the user finishes in the browser or gives up, so it belongs on
	a thread of its own.

	Args:
		on_address: Called once with the address to sign in at and whether a
			browser was opened at it, so the address can be offered to the user
			when it was not. Callable taking one str and one bool and returning
			None.

	Returns:
		str: Who is now signed in, as the settings should name them.

	Raises:
		CredentialsError: When the sign-in was not completed or was refused.
		UsageRequestError: When an endpoint could not be reached.
	"""
	answer = oauth.sign_in(OAUTH, on_address)
	token = answer.get("access_token")
	if not isinstance(token, str) or not token.strip():
		raise CredentialsError(oauth.REJECTED_MESSAGE)

	refresh = answer.get("refresh_token")
	profile = _profile(token)
	tokens = store.Tokens(
		access_token=token,
		refresh_token=refresh if isinstance(refresh, str) else "",
		expires_at=oauth.expires_at(answer),
		account=_account_name(profile),
		plan=_plan_label(profile),
	)
	store.save(KEY, tokens)
	return tokens.account


def _load_login() -> Login:
	"""Return a usable token and the plan it belongs to, renewing if it is due.

	Returns:
		Login: The bearer token and the plan label.
	"""
	tokens = oauth.usable(OAUTH)
	profile = _profile(tokens.access_token)
	if not profile:
		return Login(tokens.access_token, tokens.plan or UNKNOWN_PLAN)

	plan = _plan_label(profile)
	account = _account_name(profile)
	if plan != tokens.plan or account != tokens.account:
		# An upgrade, or a first reading after a sign-in that could not reach
		# the endpoint. Kept so the settings can name the account offline.
		tokens = store.remember(KEY, tokens, plan=plan, account=account)
	return Login(tokens.access_token, plan)


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


def start_session() -> None:
	"""Send one short message, which starts the five hour session if none is running.

	Returns:
		None.

	Raises:
		CredentialsError: When there is no sign-in to send with.
		UsageAuthError: When the sign-in was refused.
		UsageRequestError: When the endpoint could not be reached.
	"""
	token = oauth.usable(OAUTH).access_token
	post_json(
		MESSAGES_URL,
		{
			"model": SESSION_START_MODEL,
			"max_tokens": 1,
			"messages": [{"role": "user", "content": MESSAGE_TEXT}],
		},
		{**_headers(token), "anthropic-version": API_VERSION},
	)


def read() -> UsageSnapshot:
	"""Take one Claude usage reading.

	Returns:
		UsageSnapshot: The current reading.
	"""
	login = _load_login()
	return parse(fetch_json(USAGE_URL, _headers(login.token)), login.plan)
