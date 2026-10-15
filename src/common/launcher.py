"""Start the widget, the same way on every platform that runs this code.

One run watches every service, Claude and ChatGPT, the way the Mac app does, so
there is one program to start and nothing to choose on the command line. A
second copy refuses to start, because two would put two sets of identical icons
in front of the user and poll the endpoints twice as often for the same answers.

A platform's main.py installs its backend and hands over to run() below. The
widget itself is imported only after that, because the shared code asks the
backend for things as soon as it is built.
"""

from __future__ import annotations

import sys
from types import ModuleType

from .providers import PROVIDERS, Provider
from .system import claim_single_instance, detach, install
from .validation import require_type

INSTANCE_NAME = "usage-widget"
ALREADY_RUNNING_STATUS = 1


def providers() -> tuple[Provider, ...]:
	"""Return every service, in the order their tabs appear.

	Returns:
		tuple of Provider: The services, sorted by name, which is the order the
		Mac app shows its tabs in.
	"""
	return tuple(sorted(PROVIDERS.values(), key=lambda provider: provider.label))


def run(backend: ModuleType) -> int:
	"""Run the widget on a platform until the user quits it, unless one is already running.

	Args:
		backend: The platform's backend module, such as src.windows.backend.
			ModuleType.

	Returns:
		int: Process exit status, 0 on a clean exit and 1 when the widget was
		already running in another process.
	"""
	require_type(backend, ModuleType, "backend")
	install(backend)
	if not claim_single_instance(INSTANCE_NAME):
		print("FORL is already running.", file=sys.stderr)
		return ALREADY_RUNNING_STATUS
	detach(INSTANCE_NAME)
	from .ui.app import WidgetApp

	WidgetApp(providers()).run()
	return 0
