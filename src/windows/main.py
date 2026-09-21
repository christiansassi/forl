"""Entry point for the usage widget.

One run watches every service, Claude and ChatGPT, the way the Mac app does, so
there is one executable to start and nothing to choose on the command line:

	FORL.exe

A second copy refuses to start, because two would put two sets of identical
icons in front of the user and poll the endpoints twice as often for the same
answers.

A service with no sign-in stored is offered in the panel, which opens by itself
when nobody is signed in at all. The widget signs in for itself, so neither
Claude Code nor Codex need be installed.

This is the Windows widget. macOS has an application of its own, written in
Swift and built from the src/mac directory. Running this on macOS is refused
rather than half served.

Build the windowed executable with build.py so no console window appears.
The start at login switch in the settings makes it appear at sign-in.
"""

from __future__ import annotations

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
	sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.windows.providers import PROVIDERS, Provider
from src.windows.system import WINDOWS, claim_single_instance, current, detach
from src.windows.validation import require_member

INSTANCE_NAME = "usage-widget"
PLATFORMS = frozenset((WINDOWS,))
ALREADY_RUNNING_STATUS = 1
UNSUPPORTED_STATUS = 2


def providers() -> tuple[Provider, ...]:
	"""Return every service, in the order their tabs appear.

	Returns:
		tuple of Provider: The services, sorted by name, which is the order the
		Mac app shows its tabs in.
	"""
	return tuple(sorted(PROVIDERS.values(), key=lambda provider: provider.label))


def start(platform: str) -> int:
	"""Run the widget of a platform, until the user quits it.

	The widget is imported only once the platform is known, so a machine with no
	widget never reaches for the libraries one would need.

	Args:
		platform: The platform to run, which this widget serves only as WINDOWS.
			str, non-empty.

	Returns:
		int: Process exit status.
	"""
	require_member(platform, PLATFORMS, "platform")
	from src.windows.ui.app import WidgetApp

	WidgetApp(providers()).run()
	return 0


def main() -> int:
	"""Run the widget until the user quits it, unless one is already running.

	Returns:
		int: Process exit status, 0 on a clean exit, 1 when the widget was
		already running in another process, and 2 on a platform with no widget.
	"""
	if not claim_single_instance(INSTANCE_NAME):
		print("FORL is already running.", file=sys.stderr)
		return ALREADY_RUNNING_STATUS
	platform = current()
	if platform not in PLATFORMS:
		print(f"{sys.platform} is not a platform this widget runs on.", file=sys.stderr)
		return UNSUPPORTED_STATUS
	detach(INSTANCE_NAME)
	return start(platform)


if __name__ == "__main__":
	raise SystemExit(main())
