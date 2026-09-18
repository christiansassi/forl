"""Read ChatGPT usage with the sign-in the widget made for itself.

Calls the usage endpoint of the Codex backend with a token this widget obtained
in the browser and keeps in its own file, renewing it when it is close to
running out. The response reports two rolling windows, a five hour primary and a
seven day secondary, which map onto the session and weekly windows the interface
already knows, and it names the plan itself, so no second request is needed.
ChatGPT reports no split by product, so the panel simply has no product section
for this provider.

Every usage request also names the account, which the sign-in reports in the
claims of the identity token rather than as a field of its own.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from ..auth import jwt, oauth, store
from ..auth.oauth import OAuthClient
from ..usage.errors import CredentialsError, UsageAuthError, UsageRequestError
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

KEY = "chatgpt"
LABEL = "ChatGPT"

USAGE_URL = "https://chatgpt.com/backend-api/codex/usage"
USER_AGENT = "chatgpt-usage-widget/1.0"
ORIGINATOR = "codex_cli_rs"

# The port is not a free choice: this is the one the provider accepts for this
# client, so a sign-in cannot start while something else holds it.
OAUTH = OAuthClient(
	key=KEY,
	label=LABEL,
	authorize_url="https://auth.openai.com/oauth/authorize",
	token_url="https://auth.openai.com/oauth/token",
	# Public identifier of the application these endpoints were built for. A
	# client that runs on the user's machine can hold no secret, which is what
	# the proof key in the flow is for.
	client_id="app_EMoamEEZ73f0CkXaXp7hrann",
	# openid for the identity token, which is the only place the account this
	# usage is billed against is named; offline_access for the refresh token,
	# without which a sign-in lasts an hour; email for the address the settings
	# show. The tool these endpoints were built for also asks for profile, whose
	# only use here would be a display name to fall back on, so it is left out.
	scope="openid email offline_access",
	redirect_port=1455,
	redirect_path="/auth/callback",
	# Without the first, the identity token names no account and the usage
	# endpoint has nothing to bill the request against.
	authorize_extras=(
		("id_token_add_organizations", "true"),
		("codex_cli_simplified_flow", "true"),
	),
	headers=(("User-Agent", USER_AGENT), ("originator", ORIGINATOR)),
)

# Where the identity token keeps what this provider needs and a standard claim
# set does not carry.
AUTH_CLAIM = "https://api.openai.com/auth"
ACCOUNT_ID_CLAIM = "chatgpt_account_id"

# The usage endpoint answers 403 for two quite different reasons: a sign-in
# that has really gone, and a request it declines to serve for the moment. A
# token it has only just issued is refused for three to four seconds, and the
# endpoint also refuses the odd request for no reason it gives, in bursts, so
# a refused reading is tried again over a few seconds before it is believed.
AUTH_RETRY_ATTEMPTS = 5
AUTH_RETRY_DELAY_SECONDS = 1.0

REFUSED_MESSAGE = "The usage endpoint refused the request."


def _identity(answer: dict[str, Any]) -> dict[str, Any]:
	"""Return the claims of the identity token in a token endpoint answer.

	Args:
		answer: The token endpoint's answer. dict.

	Returns:
		dict[str, Any]: The claims, empty when the answer carries no identity
		token or it cannot be decoded.
	"""
	identity = answer.get("id_token")
	return jwt.claims(identity) if isinstance(identity, str) and identity.strip() else {}


def _account_id(claims: dict[str, Any]) -> str:
	"""Return the account every usage request must be made against.

	Args:
		claims: The claims of the identity token. dict.

	Returns:
		str: The account id, or an empty string when the claims carry none.
	"""
	section = claims.get(AUTH_CLAIM)
	value = section.get(ACCOUNT_ID_CLAIM) if isinstance(section, dict) else None
	return value if isinstance(value, str) else ""


def _account_name(claims: dict[str, Any]) -> str:
	"""Return who is signed in, as the settings should name them.

	Args:
		claims: The claims of the identity token. dict.

	Returns:
		str: The email address, falling back to the name, or an empty string
		when the claims carry neither.
	"""
	for field in ("email", "name"):
		value = claims.get(field)
		if isinstance(value, str) and value.strip():
			return value.strip()
	return ""


def sign_in(on_address: Callable[[str, bool], None]) -> str:
	"""Sign in to ChatGPT in the browser and store what comes back.

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
		UsageRequestError: When the token endpoint could not be reached.
	"""
	answer = oauth.sign_in(OAUTH, on_address)
	token = answer.get("access_token")
	if not isinstance(token, str) or not token.strip():
		raise CredentialsError(oauth.REJECTED_MESSAGE)

	refresh = answer.get("refresh_token")
	claims = _identity(answer)
	tokens = store.Tokens(
		access_token=token,
		refresh_token=refresh if isinstance(refresh, str) else "",
		expires_at=oauth.expires_at(answer),
		account=_account_name(claims),
		# The plan is left out because the usage response names it, so keeping
		# it here would be a second copy of something already arriving.
		extra={"account_id": _account_id(claims)},
	)
	store.save(KEY, tokens)
	return tokens.account


def _load_login() -> tuple[str, str]:
	"""Return a usable token and the account it belongs to, renewing if due.

	Returns:
		tuple[str, str]: The bearer token and the ChatGPT account id.
	"""
	tokens = oauth.usable(OAUTH)
	return tokens.access_token, tokens.extra.get("account_id", "")


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

	A refusal is only reported as an expired sign-in when the token says it has
	expired. The endpoint refuses perfectly good tokens as well, in bursts and
	for a few seconds after issuing one, and taking it at its word would tell
	the user their sign-in had run out and open a sign-in they do not need. A
	refusal that the token contradicts is reported as what it is, a request
	that did not go through, which leaves the last reading on screen and says
	nothing.

	Returns:
		UsageSnapshot: The current reading.

	Raises:
		UsageAuthError: When the sign-in has run out and must be done again.
		UsageRequestError: When the endpoint could not be reached or refused a
			token that has not expired.
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

	for attempt in range(AUTH_RETRY_ATTEMPTS):
		if attempt:
			time.sleep(AUTH_RETRY_DELAY_SECONDS)
		try:
			return parse(fetch_json(USAGE_URL, headers))
		except UsageAuthError:
			continue

	expiry = jwt.expiry(token)
	if expiry and expiry > time.time():
		raise UsageRequestError(REFUSED_MESSAGE)
	raise UsageAuthError(oauth.EXPIRED_MESSAGE)
