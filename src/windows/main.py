"""Entry point of the Windows widget.

	FORL.exe

Everything but what Windows alone does lives in src/common and is shared with
the Linux widget; this installs the Windows backend and starts it. A service
with no sign-in stored is offered in the panel, which opens by itself when
nobody is signed in at all. The widget signs in for itself, so neither Claude
Code nor Codex need be installed.

macOS has an application of its own, written in Swift and built from the
src/mac directory, and Linux has its own entry point under src/linux. Running
this anywhere but on Windows is refused rather than half served.

Build the windowed executable with build.py so no console window appears. The
start at login switch in the settings makes it appear at sign-in.
"""

from __future__ import annotations

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
	sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

UNSUPPORTED_STATUS = 2


def main() -> int:
	"""Run the widget until the user quits it.

	Returns:
		int: Process exit status, 0 on a clean exit, 1 when the widget was
		already running in another process, and 2 on a machine that is not
		Windows.
	"""
	if sys.platform != "win32":
		print("This is the Windows widget; Linux runs src/linux/main.py.", file=sys.stderr)
		return UNSUPPORTED_STATUS
	from src.common import launcher
	from src.windows import backend

	return launcher.run(backend)


if __name__ == "__main__":
	raise SystemExit(main())
