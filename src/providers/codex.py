"""Read ChatGPT usage through the login Codex stores on this machine.

Calls the usage endpoint of the Codex backend with the access token from
~/.codex/auth.json. The response reports two rolling windows, a five hour
primary and a seven day secondary, which map onto the session and weekly windows
the interface already knows. ChatGPT reports no split by product, so the panel
simply has no product section for this provider.
"""

from __future__ import annotations

import time
from typing import Any

from ..usage.errors import CredentialsError
from ..usage.http import fetch_json
from ..usage.snapshot import (
	SESSION_KEY,
	SESSION_LABEL,
	WEEKLY_KEY,
	WEEKLY_LABEL,
	UsageSnapshot,
	UsageWindow,
	clamp_percent,
	now_utc,
	parse_epoch,
)
from .local_auth import home_file, jwt_expiry, read_auth_file

USAGE_URL = "https://chatgpt.com/backend-api/codex/usage"
USER_AGENT = "chatgpt-usage-widget/1.0"
ORIGINATOR = "codex_cli_rs"

CONFIG_ENV_VAR = "CODEX_HOME"
CONFIG_DIR = ".codex"
AUTH_FILE = "auth.json"
SIGN_IN_HINT = "codex login"

EXPIRY_MARGIN_SECONDS = 60


def _load_login() -> tuple[str, str]:
	"""Read the access token and account id Codex has stored.

	Returns:
		tuple[str, str]: The bearer token and the ChatGPT account id.
	"""
	path = home_file(CONFIG_ENV_VAR, CONFIG_DIR, AUTH_FILE)
	document = read_auth_file(path, SIGN_IN_HINT)

	tokens = document.get("tokens")
	if not isinstance(tokens, dict):
		raise CredentialsError(f"Not signed in. Run '{SIGN_IN_HINT}' to sign in.")
	token = tokens.get("access_token")
	if not isinstance(token, str) or not token.strip():
		raise CredentialsError(f"Not signed in. Run '{SIGN_IN_HINT}' to sign in.")

	expiry = jwt_expiry(token)
	if expiry and expiry - time.time() < EXPIRY_MARGIN_SECONDS:
		raise CredentialsError(f"Sign-in expired. Run '{SIGN_IN_HINT}' to sign in again.")

	account_id = tokens.get("account_id")
	return token, account_id if isinstance(account_id, str) else ""


def _window(section: Any, key: str, label: str) -> UsageWindow | None:
	"""Build a usage window from one of the rate limit windows.

	Args:
		section: A window object such as primary_window. Expected dict or None.
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
		percent=clamp_percent(section.get("used_percent")),
		resets_at=parse_epoch(section.get("reset_at")),
	)


def parse(document: dict[str, Any]) -> UsageSnapshot:
	"""Build a usage snapshot from a decoded ChatGPT usage response.

	Args:
		document: The decoded JSON body returned by the usage endpoint. dict.

	Returns:
		UsageSnapshot: The parsed reading. It always carries a session window,
		reading 0 percent when the response reports none.
	"""
	plan = str(document.get("plan_type") or "unknown").replace("_", " ").title()
	rate_limit = document.get("rate_limit")
	rate_limit = rate_limit if isinstance(rate_limit, dict) else {}

	session = _window(rate_limit.get("primary_window"), SESSION_KEY, SESSION_LABEL)
	weekly = _window(rate_limit.get("secondary_window"), WEEKLY_KEY, WEEKLY_LABEL)
	if session is None:
		session = UsageWindow(key=SESSION_KEY, label=SESSION_LABEL, percent=0.0)

	credits = document.get("credits")
	credits = credits if isinstance(credits, dict) else {}
	has_credits = bool(credits.get("has_credits")) and not credits.get("unlimited")

	return UsageSnapshot(
		fetched_at=now_utc(),
		plan=plan,
		session=session,
		weekly=weekly,
		extra_label="Credit balance" if has_credits else "",
		extra_percent=100.0 if credits.get("overage_limit_reached") else 0.0 if has_credits else None,
	)


def read() -> UsageSnapshot:
	"""Take one ChatGPT usage reading.

	Returns:
		UsageSnapshot: The current reading.
	"""
	token, account_id = _load_login()
	headers = {
		"Authorization": f"Bearer {token}",
		"Accept": "application/json",
		"User-Agent": USER_AGENT,
		"originator": ORIGINATOR,
	}
	if account_id:
		headers["chatgpt-account-id"] = account_id
	return parse(fetch_json(USAGE_URL, headers, SIGN_IN_HINT))
