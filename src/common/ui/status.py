"""The readings, written to files other programs can show.

A status bar such as Waybar, Polybar or i3blocks, and a desktop widget such as
the KDE Plasma one under src/linux/plasma or the GNOME Shell extension under
src/linux/gnome, cannot ask the widget for its
readings, so the widget writes them where those programs look, every time they
change. Nothing is written on a platform whose backend names no directory for
them.

Three kinds of file go in that directory:

	status.json     every service, everything the panel knows, for widgets
	<service>.json  one service in the format Waybar's custom modules read
	<service>.txt   the same line as plain text, for Polybar and i3blocks

A bar shows the usages chosen for the tray, so it and the tray agree.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..jsonstore import write_json
from ..validation import require_type
from .core import ProviderView

STATUS_FILE = "status.json"
TEMPORARY_SUFFIX = ".tmp"

# Waybar styles a module by its class; the thresholds match where the panel's
# bars turn from green to yellow and from yellow to red.
WARNING_PERCENT = 50.0
CRITICAL_PERCENT = 80.0
SIGNED_OUT_CLASS = "signed-out"
LOADING_CLASS = "loading"


def _class_for(percent: float | None) -> str:
	"""Return the Waybar class of a reading.

	Args:
		percent: The highest share used among the shown usages, or None before a
			reading. float or None.

	Returns:
		str: "ok", "warning", "critical", or "loading" before a reading.
	"""
	if percent is None:
		return LOADING_CLASS
	if percent >= CRITICAL_PERCENT:
		return "critical"
	if percent >= WARNING_PERCENT:
		return "warning"
	return "ok"


def _service_document(view: ProviderView) -> dict[str, Any]:
	"""Return what status.json says about one service.

	Args:
		view: The state of the service. ProviderView.

	Everything the panel draws is here, so a widget can lay out the same page:
	the line under the reading and when the next one is due, the model a
	separate limit covers, which usages are products, and any extra usage.

	Returns:
		dict: The service's name, mark, plan, sign-in state, the line under the
		reading, and every usage with its share, its reset time and where the
		user chose to show it.
	"""
	snapshot = view.snapshot
	usages = []
	extra = None
	if snapshot is not None:
		scopes = {window.key: window.scope_name for window in snapshot.windows()}
		for metric in snapshot.metrics():
			usages.append(
				{
					"key": metric.key,
					"label": metric.label,
					"percent": round(metric.percent, 1),
					"resets_at": metric.resets_at.isoformat() if metric.resets_at else None,
					"group": metric.group,
					"scope": scopes.get(metric.key, ""),
					"in_panel": metric.key in view.in_panel,
					"in_tray": metric.key in view.displayed,
				}
			)
		if snapshot.extra_label and snapshot.extra_percent is not None:
			extra = {"label": snapshot.extra_label, "percent": round(snapshot.extra_percent, 1)}
	return {
		"key": view.provider.key,
		"label": view.provider.label,
		"accent": view.provider.accent,
		"logo": view.provider.logo_file,
		"plan": snapshot.plan if snapshot is not None else "",
		"signed_in": view.signed_in,
		"status": view.status,
		"refreshing": view.refreshing,
		"next_update_at": view.next_update_at.isoformat() if view.next_update_at else None,
		"usages": usages,
		"extra": extra,
	}


def _bar_line(view: ProviderView) -> tuple[str, str, float | None]:
	"""Return the line a bar shows for one service, its hover text, and its peak.

	Args:
		view: The state of the service. ProviderView.

	Returns:
		tuple: The text, such as "Claude 23% 41%", the hover text with one usage
		a line, and the highest share among the shown usages, or None before a
		reading.
	"""
	label = view.provider.label
	snapshot = view.snapshot
	if not view.signed_in:
		return (f"{label} -", f"{label}: not signed in", None)
	if snapshot is None:
		return (f"{label} ...", f"{label}: loading", None)
	metrics = [metric for metric in snapshot.metrics() if metric.key in view.displayed]
	if not metrics:
		metrics = [snapshot.metrics()[0]]
	text = f"{label} " + " ".join(f"{round(metric.percent)}%" for metric in metrics)
	tooltip = "\n".join(f"{metric.label}: {round(metric.percent)}%" for metric in snapshot.metrics())
	return (text, f"{label} {snapshot.plan}\n{tooltip}".strip(), max(metric.percent for metric in metrics))


def _write_text(path: Path, text: str) -> None:
	"""Write a text file whole, so a reader never sees half of it.

	Args:
		path: The file to replace. Path.
		text: Its new content. str.

	Returns:
		None.
	"""
	temporary = path.with_name(path.name + TEMPORARY_SUFFIX)
	temporary.write_text(text, encoding="utf-8")
	os.replace(temporary, path)


def status_document(views: tuple[ProviderView, ...], tray: bool, show_plan: bool) -> dict[str, Any]:
	"""Return everything widgets are told about every service, as one document.

	This is what status.json holds, and what the GNOME Shell extension is sent
	over the session bus.

	Args:
		views: The state of every service, in tab order. tuple of ProviderView.
		tray: Whether the widget has icons in a tray, so a widget that would
			show the same readings in the same bar can step aside. bool.
		show_plan: Whether the panel names the plan beside the service, which a
			widget drawn like the panel follows. bool.

	Returns:
		dict: When it was made, the two flags, and one entry per service.
	"""
	require_type(views, tuple, "views")
	require_type(tray, bool, "tray")
	require_type(show_plan, bool, "show_plan")
	for view in views:
		require_type(view, ProviderView, "views")
	return {
		"updated": datetime.now(timezone.utc).isoformat(),
		"tray": tray,
		"show_plan": show_plan,
		"services": [_service_document(view) for view in views],
	}


def write_status(directory: Path, views: tuple[ProviderView, ...], document: dict[str, Any]) -> bool:
	"""Write every service's readings where status bars and widgets read them.

	Args:
		directory: Where to write, created when missing. Path.
		views: The state of every service, in tab order. tuple of ProviderView.
		document: What status_document returned for those views. dict.

	Returns:
		bool: True when every file was written. False when the directory could
		not be written to, which costs the bars their reading and nothing else.
	"""
	require_type(directory, Path, "directory")
	require_type(views, tuple, "views")
	require_type(document, dict, "document")
	for view in views:
		require_type(view, ProviderView, "views")
	try:
		directory.mkdir(parents=True, exist_ok=True)
		write_json(directory / STATUS_FILE, document)
		for view in views:
			text, tooltip, peak = _bar_line(view)
			key = view.provider.key
			# One line: Waybar parses what a module prints a line at a time.
			bar = {
				"text": text,
				"tooltip": tooltip,
				"class": _class_for(peak) if view.signed_in else SIGNED_OUT_CLASS,
				"percentage": round(peak) if peak is not None else 0,
			}
			_write_text(directory / f"{key}.json", json.dumps(bar) + "\n")
			_write_text(directory / f"{key}.txt", text + "\n")
	except OSError:
		return False
	return True
