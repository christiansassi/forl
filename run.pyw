"""Entry point for the usage taskbar widget.

One run reports on one service, named by a required flag, so the two can be
started side by side:

	pythonw run.pyw --claude
	pythonw run.pyw --chatgpt

A second copy of the same service refuses to start, because two would put two
sets of identical icons in the notification area and poll the endpoint twice as
often for the same answer.

Launch it with pythonw so no console window appears. Starting it from a shortcut
in shell:startup makes the icon appear at login.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.providers import CHATGPT_KEY, CLAUDE_KEY, get_provider
from src.ui.app import WidgetApp
from src.ui.desktop import claim_single_instance

INSTANCE_NAME_PREFIX = "usage-widget-"
ALREADY_RUNNING_STATUS = 1


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
		help="report Claude usage, using the login stored by Claude Code",
	)
	group.add_argument(
		f"--{CHATGPT_KEY}",
		dest="provider",
		action="store_const",
		const=CHATGPT_KEY,
		help="report ChatGPT usage, using the login stored by Codex",
	)
	return parser.parse_args(argv).provider


def main(argv: list[str]) -> int:
	"""Run the widget until the user quits it, unless one is already running.

	Args:
		argv: Command line arguments without the program name. list of str.

	Returns:
		int: Process exit status, 0 on a clean exit and 1 when this service was
		already being watched by another process.
	"""
	provider = get_provider(parse_provider_key(argv))
	if not claim_single_instance(f"{INSTANCE_NAME_PREFIX}{provider.key}"):
		print(f"{provider.label} usage is already running.", file=sys.stderr)
		return ALREADY_RUNNING_STATUS
	WidgetApp(provider).run()
	return 0


if __name__ == "__main__":
	raise SystemExit(main(sys.argv[1:]))
