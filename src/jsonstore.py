"""Read and write the small JSON documents the widget keeps on disk.

Two kinds of file pass through here, the sign-ins the provider command line
tools store and the preferences the widget stores for itself, and both want the
same treatment: written whole under a temporary name and then moved over the
old file, which on Windows is a single operation, so a reader sees either the
old document or the new one and never a half written file.

Indentation is a tab, which is what the tools that own the sign-in files write,
so a file the widget rewrites still reads as the tool left it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .validation import require_type

TEMPORARY_SUFFIX = ".tmp"
JSON_INDENT = "	"


def read_json(path: Path) -> dict[str, Any] | None:
	"""Return the document a file holds, or None when there is nothing usable in it.

	A missing file, an unreadable one and one holding something other than a
	JSON object are all reported the same way, because the caller does the same
	thing in each case: fall back to its defaults.

	Args:
		path: The file to read. Path.

	Returns:
		dict or None: The decoded document, or None when the file is missing,
		cannot be read, or does not hold a JSON object.
	"""
	require_type(path, Path, "path")
	try:
		document = json.loads(path.read_text(encoding="utf-8"))
	except (OSError, ValueError):
		return None
	return document if isinstance(document, dict) else None


def write_json(path: Path, document: dict[str, Any]) -> None:
	"""Write a document over a file, atomically.

	The temporary file is removed when the write fails, so a failure leaves the
	directory as it was found rather than littered with partial files.

	Args:
		path: The file to replace. Its parent directory must exist. Path.
		document: The whole document to write, not only the part that changed.
			dict.

	Returns:
		None.

	Raises:
		OSError: When the document cannot be written or moved into place.
	"""
	require_type(path, Path, "path")
	require_type(document, dict, "document")

	temporary = path.with_name(path.name + TEMPORARY_SUFFIX)
	try:
		temporary.write_text(json.dumps(document, indent=JSON_INDENT), encoding="utf-8")
		os.replace(temporary, path)
	except OSError:
		temporary.unlink(missing_ok=True)
		raise
