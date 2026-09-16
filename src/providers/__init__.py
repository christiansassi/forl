"""The services the widget can report on, and how to pick one.

A provider is everything that differs between Claude and ChatGPT: where the
sign-in is stored, which endpoint reports usage, how that response is shaped,
and how the product is named and colored. Everything after the provider, the
icons, the panel and the polling, is shared.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..usage.snapshot import UsageSnapshot
from ..validation import require_member, require_non_empty_str
from . import claude, codex

CLAUDE_KEY = "claude"
CHATGPT_KEY = "chatgpt"


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
		read: Takes one usage reading. Callable taking no arguments and returning
			a UsageSnapshot; raises CredentialsError or UsageRequestError.
	"""

	key: str
	label: str
	logo_file: str
	accent: str
	read: Callable[[], UsageSnapshot]


PROVIDERS = {
	CLAUDE_KEY: Provider(
		key=CLAUDE_KEY,
		label="Claude",
		logo_file="claude.svg",
		accent="#d97757",
		read=claude.read,
	),
	CHATGPT_KEY: Provider(
		key=CHATGPT_KEY,
		label="ChatGPT",
		logo_file="chatgpt.svg",
		accent="#ffffff",
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
