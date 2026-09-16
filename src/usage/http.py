"""The one HTTP call shape the widget makes.

Both providers answer a plain authenticated GET with a JSON document, so the
request, the error mapping and the decoding live here once.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..validation import require_non_empty_str, require_number_in_range, require_type
from .errors import UsageAuthError, UsageRequestError


def fetch_json(
	url: str,
	headers: dict[str, str],
	sign_in_hint: str,
	timeout: float = 15.0,
) -> dict[str, Any]:
	"""Request a JSON document and return it decoded.

	Args:
		url: The endpoint to read. str, non-empty.
		headers: Request headers, including the authorization header. dict of str
			to str.
		sign_in_hint: The command that signs the user in again, named in the
			error when the endpoint rejects the token. str, non-empty.
		timeout: Socket timeout for the request in seconds. float, between 1 and 120.

	Returns:
		dict[str, Any]: The decoded JSON body.
	"""
	require_non_empty_str(url, "url")
	require_type(headers, dict, "headers")
	require_non_empty_str(sign_in_hint, "sign_in_hint")
	require_number_in_range(timeout, 1.0, 120.0, "timeout")

	request = urllib.request.Request(url, headers=headers, method="GET")
	try:
		with urllib.request.urlopen(request, timeout=timeout) as response:
			body = response.read()
	except urllib.error.HTTPError as exc:
		if exc.code in (401, 403):
			raise UsageAuthError(f"Sign-in expired. Run '{sign_in_hint}' to sign in again.") from exc
		raise UsageRequestError(f"Usage request failed with HTTP {exc.code}.") from exc
	except urllib.error.URLError as exc:
		raise UsageRequestError(f"Usage request failed: {exc.reason}") from exc
	except TimeoutError as exc:
		raise UsageRequestError(f"Usage request timed out after {timeout:g}s.") from exc

	try:
		document = json.loads(body)
	except json.JSONDecodeError as exc:
		raise UsageRequestError(f"Usage endpoint returned invalid JSON: {exc}") from exc
	if not isinstance(document, dict):
		raise UsageRequestError("Usage endpoint returned an unexpected payload shape.")
	return document
