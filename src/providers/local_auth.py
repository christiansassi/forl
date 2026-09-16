"""Read the sign-in that a provider command line tool has already stored.

The widget never performs its own login. It reuses the token that Claude Code or
Codex wrote to disk and re-reads that file before every poll, so a token the
tool has refreshed is picked up without restarting the widget. What the two
files have in common, being JSON at a path under the home directory and holding
a token with an expiry, is handled here.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
from typing import Any

from ..usage.errors import CredentialsError
from ..validation import require_non_empty_str, require_type


def home_file(env_var: str, default_dir: str, file_name: str) -> Path:
	"""Return the path of a tool's configuration file for the current user.

	Honors the tool's own environment variable so the widget follows a relocated
	configuration directory.

	Args:
		env_var: Name of the variable that overrides the directory, such as
			"CLAUDE_CONFIG_DIR". str, non-empty.
		default_dir: Directory under the home directory to fall back to, such as
			".claude". str, non-empty.
		file_name: Name of the file inside that directory. str, non-empty.

	Returns:
		Path: Absolute path to the file, which may not exist.
	"""
	require_non_empty_str(env_var, "env_var")
	require_non_empty_str(default_dir, "default_dir")
	require_non_empty_str(file_name, "file_name")

	configured = os.environ.get(env_var)
	base = Path(configured).expanduser() if configured else Path.home() / default_dir
	return base / file_name


def read_auth_file(path: Path, sign_in_hint: str) -> dict[str, Any]:
	"""Read and decode a tool's stored sign-in.

	Args:
		path: The file to read. Path.
		sign_in_hint: What the user should run to sign in, quoted in the error
			message when the file is missing or unusable. str, non-empty.

	Returns:
		dict[str, Any]: The decoded JSON document.
	"""
	require_type(path, Path, "path")
	require_non_empty_str(sign_in_hint, "sign_in_hint")

	try:
		raw = path.read_text(encoding="utf-8")
	except FileNotFoundError as exc:
		raise CredentialsError(f"Not signed in. Run '{sign_in_hint}' to sign in.") from exc
	except OSError as exc:
		raise CredentialsError(f"Cannot read {path}: {exc}") from exc

	try:
		document = json.loads(raw)
	except json.JSONDecodeError as exc:
		raise CredentialsError(f"{path} is not valid JSON: {exc}") from exc
	if not isinstance(document, dict):
		raise CredentialsError(f"Not signed in. Run '{sign_in_hint}' to sign in.")
	return document


def jwt_expiry(token: str) -> float:
	"""Return the expiry claim of a JSON web token as a Unix timestamp.

	Only the payload is read, and only for its expiry; the signature is the
	endpoint's business, not the widget's.

	Args:
		token: The encoded token. str, non-empty.

	Returns:
		float: The expiry in seconds since the epoch, or 0.0 when the token
		carries none or cannot be decoded.
	"""
	require_non_empty_str(token, "token")
	parts = token.split(".")
	if len(parts) < 2:
		return 0.0
	payload = parts[1] + "=" * (-len(parts[1]) % 4)
	try:
		claims = json.loads(base64.urlsafe_b64decode(payload))
	except (binascii.Error, ValueError, UnicodeDecodeError):
		return 0.0
	expiry = claims.get("exp") if isinstance(claims, dict) else None
	return float(expiry) if isinstance(expiry, (int, float)) else 0.0
