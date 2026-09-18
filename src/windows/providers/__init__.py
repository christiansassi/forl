"""The services the widget can report on, and how to pick one.

A provider is everything that differs between Claude and ChatGPT: how the
sign-in is obtained, which endpoint reports usage, how that response is shaped,
and how the product is named and colored. Everything after the provider, the
icons, the panel and the polling, is shared.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..auth.oauth import OAuthClient
from ..usage.snapshot import UsageSnapshot
from ..validation import require_member, require_non_empty_str
from . import claude, codex

# Named here as well as on the provider records, because the command line is
# built from them before any provider has been chosen.
CLAUDE_KEY = claude.KEY
CHATGPT_KEY = codex.KEY


@dataclass(frozen=True)
class Provider:
	"""One service the widget can report on.

	Attributes:
		key: Stable identifier used on the command line and in window names. str.
		label: Product name shown in the panel title. str.
		logo_file: Name of the mark inside the assets directory. str.
		accent: Brand color as a "#rrggbb" string, used for the mark and the
			controls but never for a value. The OpenAI mark is monochrome, so
			ChatGPT takes white rather than a hue. str.
		oauth: What this service's browser sign-in needs. Held on the provider so
			the application can name the port a sign-in wants without knowing
			which service it is talking to. OAuthClient.
		sign_in: Runs the browser sign-in and stores the result, returning who is
			now signed in. Takes a callback, which it calls once with the address
			to sign in at and whether a browser was opened at it. Blocks for as
			long as the user takes. Callable taking one callable and returning
			str; raises CredentialsError or UsageRequestError.
		read: Takes one usage reading. Callable taking no arguments and returning
			a UsageSnapshot; raises CredentialsError or UsageRequestError.
	"""

	key: str
	label: str
	logo_file: str
	accent: str
	oauth: OAuthClient
	sign_in: Callable[[Callable[[str, bool], None]], str]
	read: Callable[[], UsageSnapshot]


PROVIDERS = {
	CLAUDE_KEY: Provider(
		key=CLAUDE_KEY,
		label=claude.LABEL,
		logo_file="claude.svg",
		accent="#d97757",
		oauth=claude.OAUTH,
		sign_in=claude.sign_in,
		read=claude.read,
	),
	CHATGPT_KEY: Provider(
		key=CHATGPT_KEY,
		label=codex.LABEL,
		logo_file="chatgpt.svg",
		accent="#ffffff",
		oauth=codex.OAUTH,
		sign_in=codex.sign_in,
		read=codex.read,
	),
}

PROVIDER_KEYS = frozenset(PROVIDERS)


def get_provider(key: str) -> Provider:
	"""Return the provider with a given key.

	Args:
		key: One of the keys of PROVIDERS, such as "claude". str, non-empty.

	Returns:
		Provider: The matching provider.
	"""
	require_non_empty_str(key, "key")
	require_member(key, PROVIDER_KEYS, "key")
	return PROVIDERS[key]
