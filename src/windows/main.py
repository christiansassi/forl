"""Entry point for the usage widget.

One run reports on one service, named by a required flag, so the two can be
started side by side:

	FORL.exe --claude
	FORL.exe --chatgpt

A second copy of the same service refuses to start, because two would put two
sets of identical icons in front of the user and poll the endpoint twice as
often for the same answer.

A run with no sign-in stored for the service opens the browser to get one. The
widget signs in for itself, so neither Claude Code nor Codex need be installed.

This is the Windows widget. macOS has an application of its own, written in
Swift and built from the src/mac directory, which watches both services at once and
puts their readings in the menu bar, on the Dock icon, in real widgets and in
Control Center. Running this on macOS is refused rather than half served.

Build the windowed executable with build.py so no console window appears.
The start on startup switch in the settings makes it appear at sign-in.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
	sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.windows.providers import CHATGPT_KEY, CLAUDE_KEY, Provider, get_provider
from src.windows.system import WINDOWS, claim_single_instance, current, detach
from src.windows.validation import require_member

INSTANCE_NAME_PREFIX = "usage-widget-"
PLATFORMS = frozenset((WINDOWS,))
ALREADY_RUNNING_STATUS = 1
UNSUPPORTED_STATUS = 2


def parse_provider_key(argv: list[str]) -> str:
	"""Return the provider key named on the command line.

	Exactly one flag must be given: there is no default, because which service
	is being watched should never be a guess.

	Args:
		argv: Command line arguments without the program name. list of str.

	Returns:
		str: The chosen provider key.
	"""
	parser = argparse.ArgumentParser(
		prog="FORL.exe",
		description="Show Claude or ChatGPT usage in the Windows notification area.",
	)
	group = parser.add_mutually_exclusive_group(required=True)
	group.add_argument(
		f"--{CLAUDE_KEY}",
		dest="provider",
		action="store_const",
		const=CLAUDE_KEY,
		help="report Claude usage",
	)
	group.add_argument(
		f"--{CHATGPT_KEY}",
		dest="provider",
		action="store_const",
		const=CHATGPT_KEY,
		help="report ChatGPT usage",
	)
	return parser.parse_args(argv).provider


def start(platform: str, provider: Provider) -> int:
	"""Run the widget of a platform, until the user quits it.

	The widget is imported only once the platform is known, so a machine with no
	widget never reaches for the libraries one would need.

	Args:
		platform: The platform to run, which this widget serves only as WINDOWS.
			str, non-empty.
		provider: The service to report on. Provider.

	Returns:
		int: Process exit status.
	"""
	require_member(platform, PLATFORMS, "platform")
	from src.windows.ui.app import WidgetApp

	WidgetApp(provider).run()
	return 0


def main(argv: list[str]) -> int:
	"""Run the widget until the user quits it, unless one is already running.

	Args:
		argv: Command line arguments without the program name. list of str.

	Returns:
		int: Process exit status, 0 on a clean exit, 1 when this service was
		already being watched by another process, and 2 on a platform with no
		widget.
	"""
	provider = get_provider(parse_provider_key(argv))
	name = f"{INSTANCE_NAME_PREFIX}{provider.key}"
	if not claim_single_instance(name):
		print(f"{provider.label} usage is already running.", file=sys.stderr)
		return ALREADY_RUNNING_STATUS
	platform = current()
	if platform not in PLATFORMS:
		print(f"{sys.platform} is not a platform this widget runs on.", file=sys.stderr)
		return UNSUPPORTED_STATUS
	detach(name)
	return start(platform, provider)


if __name__ == "__main__":
	raise SystemExit(main(sys.argv[1:]))
