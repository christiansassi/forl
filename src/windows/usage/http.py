"""The HTTP calls the widget makes.

Both providers answer a plain authenticated GET with a JSON document, both
renew a sign-in with a plain form encoded POST, and both take a message as a
JSON POST, so the requests, the error mapping and the decoding live here once.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..validation import require_non_empty_str, require_number_in_range, require_type
from .errors import UsageAuthError, UsageRequestError


def _decode(body: bytes) -> dict[str, Any]:
	"""Return a response body decoded as a JSON object.

	Args:
		body: The bytes the endpoint returned. bytes.

	Returns:
		dict[str, Any]: The decoded object.
	"""
	try:
		document = json.loads(body)
	except json.JSONDecodeError as exc:
		raise UsageRequestError(f"Endpoint returned invalid JSON: {exc}") from exc
	if not isinstance(document, dict):
		raise UsageRequestError("Endpoint returned an unexpected payload shape.")
	return document


def _reason(error: urllib.error.HTTPError) -> str:
	"""Return what an endpoint said about a refusal, as short text.

	Args:
		error: The failure raised by urllib. urllib.error.HTTPError.

	Returns:
		str: The error name the endpoint gave, or the start of its body.
	"""
	try:
		body = error.read()
	except OSError:
		return ""
	try:
		document = json.loads(body)
	except json.JSONDecodeError:
		return body[:200].decode("utf-8", "replace")
	if isinstance(document, dict):
		named = document.get("error") or document.get("detail") or document.get("message")
		if named:
			return str(named)
	return str(document)[:200]


def _exchange(request: urllib.request.Request, timeout: float) -> bytes:
	"""Make one request and return its body, read to the end.

	Args:
		request: The prepared request. urllib.request.Request.
		timeout: Socket timeout in seconds. float.

	Returns:
		bytes: The body of the answer.
	"""
	try:
		with urllib.request.urlopen(request, timeout=timeout) as response:
			return response.read()
	except urllib.error.HTTPError as exc:
		# What the endpoint said goes to the error stream rather than to the
		# panel: "invalid_client" and "invalid_grant" mean very different things
		# to whoever is debugging, and neither means anything to the user.
		print(f"{request.full_url} -> HTTP {exc.code} {_reason(exc)}", file=sys.stderr)
		if exc.code in (400, 401, 403):
			raise UsageAuthError("Sign-in expired.") from exc
		raise UsageRequestError(f"Request failed with HTTP {exc.code}.") from exc
	except urllib.error.URLError as exc:
		raise UsageRequestError(f"Request failed: {exc.reason}") from exc
	except TimeoutError as exc:
		raise UsageRequestError(f"Request timed out after {timeout:g}s.") from exc


def _send(request: urllib.request.Request, timeout: float) -> dict[str, Any]:
	"""Make one request and return the decoded JSON body.

	Args:
		request: The prepared request. urllib.request.Request.
		timeout: Socket timeout in seconds. float.

	Returns:
		dict[str, Any]: The decoded JSON body.
	"""
	return _decode(_exchange(request, timeout))


def post_json(
	url: str,
	payload: dict[str, Any],
	headers: dict[str, str],
	timeout: float = 60.0,
) -> bytes:
	"""Send a JSON POST and return the answer's body, read to the end.

	The body is returned undecoded, because one of the endpoints this sends to
	answers with a stream of events rather than one JSON document, and reading
	it to the end is what lets the request finish.

	Args:
		url: The endpoint to post to. str, non-empty.
		payload: The document to send. dict.
		headers: Request headers, including the authorization header. dict of
			str to str.
		timeout: Socket timeout for the request in seconds. float, between 1 and 120.

	Returns:
		bytes: The body of the answer.
	"""
	require_non_empty_str(url, "url")
	require_type(payload, dict, "payload")
	require_type(headers, dict, "headers")
	require_number_in_range(timeout, 1.0, 120.0, "timeout")

	request = urllib.request.Request(
		url,
		data=json.dumps(payload).encode("utf-8"),
		headers={"Content-Type": "application/json", **headers},
		method="POST",
	)
	return _exchange(request, timeout)


def post_form(
	url: str,
	fields: dict[str, str],
	headers: dict[str, str],
	timeout: float = 15.0,
) -> dict[str, Any]:
	"""Send a form encoded POST and return the decoded JSON answer.

	This is the shape an OAuth token endpoint takes: the POST that gets or
	renews a sign-in.

	Args:
		url: The endpoint to post to. str, non-empty.
		fields: The form fields to send. dict of str to str.
		headers: Request headers to add, of which the user agent matters: an
			endpoint behind a bot check refuses a request that does not name the
			client making it. dict of str to str.
		timeout: Socket timeout for the request in seconds. float, between 1 and 120.

	Returns:
		dict[str, Any]: The decoded JSON body.
	"""
	require_non_empty_str(url, "url")
	require_type(fields, dict, "fields")
	require_type(headers, dict, "headers")
	require_number_in_range(timeout, 1.0, 120.0, "timeout")

	request = urllib.request.Request(
		url,
		data=urllib.parse.urlencode(fields).encode("utf-8"),
		headers={
			"Content-Type": "application/x-www-form-urlencoded",
			"Accept": "application/json",
			**headers,
		},
		method="POST",
	)
	return _send(request, timeout)


def fetch_json(
	url: str,
	headers: dict[str, str],
	timeout: float = 15.0,
) -> dict[str, Any]:
	"""Request a JSON document and return it decoded.

	Args:
		url: The endpoint to read. str, non-empty.
		headers: Request headers, including the authorization header. dict of str
			to str.
		timeout: Socket timeout for the request in seconds. float, between 1 and 120.

	Returns:
		dict[str, Any]: The decoded JSON body.
	"""
	require_non_empty_str(url, "url")
	require_type(headers, dict, "headers")
	require_number_in_range(timeout, 1.0, 120.0, "timeout")

	return _send(urllib.request.Request(url, headers=headers, method="GET"), timeout)
