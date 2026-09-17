"""Entry point for the usage widget.

One run reports on one service, named by a required flag, so the two can be
started side by side:

	pythonw run.pyw --claude
	pythonw run.pyw --chatgpt

A second copy of the same service refuses to start, because two would put two
sets of identical icons in front of the user and poll the endpoint twice as
often for the same answer.

A run with no sign-in stored for the service opens the browser to get one. The
widget signs in for itself, so neither Claude Code nor Codex need be installed.

The widget itself is chosen by the platform. Windows gets the notification area
widget; macOS gets its own, which is not built yet. The two are picked apart
here rather than inside the widget, so neither imports what the other needs.

On Windows, launch it with pythonw so no console window appears. The start on
startup switch in the settings makes it appear at sign-in.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.providers import CHATGPT_KEY, CLAUDE_KEY, Provider, get_provider
from src.system import MACOS, WINDOWS, claim_single_instance, current

INSTANCE_NAME_PREFIX = "usage-widget-"
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
		prog="run.pyw",
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


def start(provider: Provider) -> int:
	"""Run the widget this platform has, until the user quits it.

	The widget is imported only once its platform is known, because each one
	reaches for libraries the other has no use for.

	Args:
		provider: The service to report on. Provider.

	Returns:
		int: Process exit status.
	"""
	platform = current()
	if platform == WINDOWS:
		from src.ui.app import WidgetApp

		WidgetApp(provider).run()
		return 0
	if platform == MACOS:
		from src.ui.macos import run_widget

		return run_widget(provider)
	print(f"{sys.platform} is not a platform this widget runs on.", file=sys.stderr)
	return UNSUPPORTED_STATUS


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
	if not claim_single_instance(f"{INSTANCE_NAME_PREFIX}{provider.key}"):
		print(f"{provider.label} usage is already running.", file=sys.stderr)
		return ALREADY_RUNNING_STATUS
	return start(provider)


if __name__ == "__main__":
	raise SystemExit(main(sys.argv[1:]))
