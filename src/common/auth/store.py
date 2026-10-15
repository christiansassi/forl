"""Where the widget keeps the sign-in it made for itself.

One file holds both providers, keyed by provider key, beside the preferences
file and written the same careful way: whole, under a temporary name, then
moved into place, and re-read before each write so the other widget's section
survives.

The file holds refresh tokens, which are the sign-in itself, so it lives under
the per user application data directory src.paths names. On Windows and on macOS
that directory is already readable only by the user it belongs to and by
administrators, which is the same protection the tools' own credential files
get.

Unlike the preferences, a sign-in that cannot be written is reported. A renewal
retires the token it was given, so a token obtained and not stored is a sign-in
lost, and the user must be told to do it again rather than left wondering why
the reading stopped.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..jsonstore import read_json, write_json
from ..paths import data_file
from ..usage.errors import CredentialsError
from ..validation import require_non_empty_str, require_type

CREDENTIALS_FILE = "credentials.json"

ACCESS_FIELD = "access_token"
REFRESH_FIELD = "refresh_token"
EXPIRES_FIELD = "expires_at"
ACCOUNT_FIELD = "account"
PLAN_FIELD = "plan"
EXTRA_FIELD = "extra"


@dataclass(frozen=True)
class Tokens:
	"""One provider's stored sign-in.

	Attributes:
		access_token: What is sent to the usage endpoint. str.
		refresh_token: What is exchanged for a new access token. Empty when the
			provider issued none, which leaves signing in again the only way
			back. str.
		expires_at: When the access token stops being accepted, in seconds since
			the epoch. 0.0 when the provider said nothing about it. float.
		account: Who is signed in, as it is shown in the settings, usually an
			email address. str.
		plan: The plan as it is shown in the panel, such as "Max 5x". Stored
			rather than looked up, so a reading costs one request. str.
		extra: Anything one provider needs and the other does not, such as the
			account id ChatGPT wants on every usage request. dict of str to str.
	"""

	access_token: str
	refresh_token: str = ""
	expires_at: float = 0.0
	account: str = ""
	plan: str = ""
	extra: dict[str, str] = None

	def __post_init__(self) -> None:
		"""Give `extra` an empty dictionary of its own when none was passed.

		A mutable default on the class would be shared by every instance, so it
		is filled in here instead.

		Returns:
			None.
		"""
		if self.extra is None:
			object.__setattr__(self, "extra", {})


def credentials_path() -> Path:
	"""Return the file the sign-ins of every provider are kept in.

	Returns:
		Path: The path, whose parent may not exist yet.
	"""
	return data_file(CREDENTIALS_FILE)


def _text(section: dict[str, Any], field: str) -> str:
	"""Return one string field of a stored section.

	Args:
		section: The stored section. dict.
		field: Name of the field to read. str, non-empty.

	Returns:
		str: The value, or an empty string when it is missing or not a string.
	"""
	value = section.get(field)
	return value if isinstance(value, str) else ""


def load(provider_key: str) -> Tokens | None:
	"""Return the stored sign-in of one provider.

	Every field is checked rather than trusted: the file is editable by hand,
	and a bad value should cost that one field and not the launch.

	Args:
		provider_key: Key of the provider, such as "claude". str, non-empty.

	Returns:
		Tokens or None: The sign-in, or None when there is none stored or it
		carries no access token, which are the same thing to a caller.
	"""
	require_non_empty_str(provider_key, "provider_key")

	document = read_json(credentials_path()) or {}
	section = document.get(provider_key)
	if not isinstance(section, dict):
		return None

	access = _text(section, ACCESS_FIELD)
	if not access.strip():
		return None

	expires_at = section.get(EXPIRES_FIELD)
	extra = section.get(EXTRA_FIELD)
	return Tokens(
		access_token=access,
		refresh_token=_text(section, REFRESH_FIELD),
		expires_at=float(expires_at) if isinstance(expires_at, (int, float)) else 0.0,
		account=_text(section, ACCOUNT_FIELD),
		plan=_text(section, PLAN_FIELD),
		extra=(
			{key: value for key, value in extra.items() if isinstance(key, str) and isinstance(value, str)}
			if isinstance(extra, dict)
			else {}
		),
	)


def save(provider_key: str, tokens: Tokens) -> None:
	"""Store the sign-in of one provider, leaving the other's section alone.

	Args:
		provider_key: Key of the provider, such as "claude". str, non-empty.
		tokens: The sign-in to store. Tokens.

	Returns:
		None.

	Raises:
		CredentialsError: When the file cannot be written, which would lose the
			sign-in the caller has just obtained.
	"""
	require_non_empty_str(provider_key, "provider_key")
	require_type(tokens, Tokens, "tokens")

	path = credentials_path()
	document = read_json(path) or {}
	document[provider_key] = {
		ACCESS_FIELD: tokens.access_token,
		REFRESH_FIELD: tokens.refresh_token,
		EXPIRES_FIELD: tokens.expires_at,
		ACCOUNT_FIELD: tokens.account,
		PLAN_FIELD: tokens.plan,
		EXTRA_FIELD: dict(tokens.extra),
	}
	try:
		path.parent.mkdir(parents=True, exist_ok=True)
		write_json(path, document)
	except OSError as exc:
		raise CredentialsError(f"Cannot write {path}: {exc}") from exc


def clear(provider_key: str) -> None:
	"""Forget one provider's sign-in, leaving the other's alone.

	Args:
		provider_key: Key of the provider, such as "claude". str, non-empty.

	Returns:
		None. A file that cannot be written leaves the sign-in in place, which
		the caller sees for itself the next time it loads.
	"""
	require_non_empty_str(provider_key, "provider_key")

	path = credentials_path()
	document = read_json(path)
	if not document or provider_key not in document:
		return
	document.pop(provider_key)
	try:
		write_json(path, document)
	except OSError:
		return


def remember(provider_key: str, tokens: Tokens, **fields: Any) -> Tokens:
	"""Store a sign-in with some of its fields replaced, and return it.

	Used by a renewal, which changes the tokens and nothing the user sees.

	Args:
		provider_key: Key of the provider, such as "claude". str, non-empty.
		tokens: The sign-in to start from. Tokens.
		**fields: Fields of Tokens to replace. Any.

	Returns:
		Tokens: What was stored.

	Raises:
		CredentialsError: When the file cannot be written.
	"""
	updated = replace(tokens, **fields)
	save(provider_key, updated)
	return updated
