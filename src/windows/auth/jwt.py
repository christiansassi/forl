"""Read what a JSON web token says about itself.

Only the payload is decoded, and only for what the widget needs from it: when
the token expires, and, for ChatGPT, which account and plan it was issued for.
The signature is the endpoint's business. Nothing here is a security check: a
token this module has read is still only trusted because the endpoint that
issued it handed it over, and because the endpoint that receives it will check
the signature itself.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from ..validation import require_non_empty_str

# The part of a "header.payload.signature" token that carries the claims.
PAYLOAD_PART = 1


def claims(token: str) -> dict[str, Any]:
	"""Return the claims a token carries.

	Args:
		token: The encoded token. str, non-empty.

	Returns:
		dict[str, Any]: The decoded claims, empty when the token is not a JSON
		web token or its payload cannot be decoded.
	"""
	require_non_empty_str(token, "token")
	parts = token.split(".")
	if len(parts) <= PAYLOAD_PART:
		return {}

	encoded = parts[PAYLOAD_PART]
	# The payload is base64 with its padding stripped, which the decoder needs
	# back before it will accept the text.
	padded = encoded + "=" * (-len(encoded) % 4)
	try:
		decoded = json.loads(base64.urlsafe_b64decode(padded))
	except (binascii.Error, ValueError, UnicodeDecodeError):
		return {}
	return decoded if isinstance(decoded, dict) else {}


def expiry(token: str) -> float:
	"""Return the expiry claim of a token as a Unix timestamp.

	Args:
		token: The encoded token. str, non-empty.

	Returns:
		float: The expiry in seconds since the epoch, or 0.0 when the token
		carries none or cannot be decoded.
	"""
	moment = claims(token).get("exp")
	return float(moment) if isinstance(moment, (int, float)) else 0.0
