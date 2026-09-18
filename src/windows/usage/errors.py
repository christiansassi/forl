"""Failures the widget expects and reports rather than crashes on.

Both providers fail in the same two ways, a login that cannot be read and a
request that does not come back, so both raise the errors defined here.
"""

from __future__ import annotations


class CredentialsError(RuntimeError):
	"""Raised when the local sign-in of a provider cannot be read or is unusable."""


class UsageRequestError(RuntimeError):
	"""Raised when a usage endpoint cannot be reached or refuses the request."""


class UsageAuthError(UsageRequestError):
	"""Raised when a usage endpoint rejects the token, so a new sign-in is needed."""
