"""Proof key for code exchange, which is what lets a client keep no secret.

A widget installed on a user's machine cannot hold a client secret: anything
shipped with it is readable by anyone who has it. Instead of a secret, the
authorization request carries the hash of a freshly made random string and the
code exchange carries the string itself. An authorization code intercepted on
its way back is then worth nothing without the string, which never left this
process.

Values are base64 encoded in the URL safe alphabet with the padding removed,
which is the encoding RFC 7636 specifies.
"""

from __future__ import annotations

import base64
import hashlib
import secrets

from ..validation import require_non_empty_str

# Length of the random material behind each value. The specification allows a
# verifier of 43 to 128 characters; 32 bytes encodes to 43, which is the floor
# and is already 256 bits. The state is the same length, not because it needs to
# be, but because one of the endpoints answers "invalid request format" to a
# shorter one and says nothing else about it.
VERIFIER_BYTES = 32
STATE_BYTES = 32


def _encode(raw: bytes) -> str:
	"""Return bytes in the URL safe base64 alphabet without padding.

	Args:
		raw: The bytes to encode. bytes.

	Returns:
		str: The encoded text, which contains no character needing escaping in
		a query string.
	"""
	return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def verifier() -> str:
	"""Return a fresh code verifier.

	Returns:
		str: 43 characters of URL safe base64, to be sent with the code
		exchange and never before it.
	"""
	return _encode(secrets.token_bytes(VERIFIER_BYTES))


def challenge(code_verifier: str) -> str:
	"""Return the challenge that goes with a verifier.

	Args:
		code_verifier: The verifier to hash, as `verifier` returned it. str,
			non-empty.

	Returns:
		str: The SHA-256 hash of the verifier, encoded the same way, to be sent
		with the authorization request.
	"""
	require_non_empty_str(code_verifier, "code_verifier")
	return _encode(hashlib.sha256(code_verifier.encode("ascii")).digest())


def state() -> str:
	"""Return a fresh state value.

	The provider echoes this back with the code, and a redirect carrying
	anything else did not come from the request this process made.

	Returns:
		str: 43 characters of URL safe base64.
	"""
	return _encode(secrets.token_bytes(STATE_BYTES))
