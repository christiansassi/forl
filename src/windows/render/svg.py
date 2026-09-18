"""Read the outline of a provider mark out of its SVG.

Both marks ship as a single path element, so it is cheaper to read that path
directly than to carry an SVG rendering library. The path is split into its
subpaths and each one is flattened to a polygon, which is a shape any toolkit
can fill: the Windows panel fills them with Pillow, the macOS surfaces with a
Cocoa path.

Nothing here draws, and nothing here imports a drawing library, which is what
lets each platform install only the one it uses.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path

from ..validation import require_non_empty_str, require_positive_int
from .curves import cubic_points

ASSETS_DIR = Path(__file__).resolve().parents[2] / "common" / "assets"
ARC_SEGMENTS = 12
CURVE_SEGMENTS = 16

PATH_DATA_PATTERN = re.compile(r"\sd=\"([^\"]+)\"")
VIEW_BOX_PATTERN = re.compile(r"viewBox=\"([^\"]+)\"")
NUMBER_PATTERN = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
COMMAND_PATTERN = re.compile(r"[A-Za-z]")

SUPPORTED_COMMANDS = frozenset("MmLlHhVvCcSsAaZz")


class _PathReader:
	"""Walk the characters of an SVG path, handing back numbers and arc flags.

	A separate reader is needed because arc flags may be written without any
	separator, as in "01-.104", where a plain number scan would read "01" as one
	value.
	"""

	def __init__(self, data: str) -> None:
		"""Start reading at the beginning of a path.

		Args:
			data: The path data of an SVG "d" attribute. str, non-empty.

		Returns:
			None.
		"""
		require_non_empty_str(data, "data")
		self._data = data
		self._index = 0

	def _skip_separators(self) -> None:
		"""Advance past any whitespace and commas.

		Returns:
			None.
		"""
		while self._index < len(self._data) and self._data[self._index] in " \t\r\n,":
			self._index += 1

	@property
	def done(self) -> bool:
		"""Return whether the whole path has been read.

		Returns:
			bool: True once no characters remain.
		"""
		self._skip_separators()
		return self._index >= len(self._data)

	def command(self) -> str | None:
		"""Return the next command letter, or None when a number comes next.

		A repeated command letter may be left out in SVG, so the caller keeps the
		previous one when this returns None.

		Returns:
			str or None: The command letter, consumed from the path.
		"""
		self._skip_separators()
		if self._index < len(self._data) and COMMAND_PATTERN.match(self._data, self._index):
			letter = self._data[self._index]
			self._index += 1
			return letter
		return None

	def number(self) -> float:
		"""Return the next number in the path.

		Returns:
			float: The value, consumed from the path.
		"""
		self._skip_separators()
		match = NUMBER_PATTERN.match(self._data, self._index)
		if match is None:
			raise ValueError(f"Expected a number at offset {self._index} of the path")
		self._index = match.end()
		return float(match.group(0))

	def point(self, origin: tuple[float, float]) -> tuple[float, float]:
		"""Return the next pair of numbers as a point offset from an origin.

		Args:
			origin: Point relative coordinates are measured from, which is the
				zero point for an absolute command. tuple of two floats.

		Returns:
			tuple[float, float]: The point, consumed from the path.
		"""
		return (origin[0] + self.number(), origin[1] + self.number())

	def flag(self) -> bool:
		"""Return the next arc flag, which is a single "0" or "1".

		Returns:
			bool: True for "1".
		"""
		self._skip_separators()
		if self._index >= len(self._data) or self._data[self._index] not in "01":
			raise ValueError(f"Expected an arc flag at offset {self._index} of the path")
		value = self._data[self._index] == "1"
		self._index += 1
		return value


def _arc_points(
	start: tuple[float, float],
	end: tuple[float, float],
	radii: tuple[float, float],
	rotation: float,
	large_arc: bool,
	sweep: bool,
) -> list[tuple[float, float]]:
	"""Flatten an SVG elliptical arc into a list of points.

	Implements the endpoint to center conversion from the SVG specification, then
	samples the resulting sweep at a fixed number of steps.

	Args:
		start: Where the arc begins as (x, y). tuple of two floats.
		end: Where the arc ends as (x, y). tuple of two floats.
		radii: The ellipse radii as (rx, ry). tuple of two floats.
		rotation: Rotation of the ellipse in degrees. float.
		large_arc: Whether to take the longer of the two sweeps. bool.
		sweep: Whether to travel in the direction of increasing angle. bool.

	Returns:
		list of tuple[float, float]: The sampled points, excluding the start.
	"""
	rx, ry = abs(radii[0]), abs(radii[1])
	if rx == 0.0 or ry == 0.0:
		return [end]

	angle = math.radians(rotation)
	cos_a, sin_a = math.cos(angle), math.sin(angle)
	dx2 = (start[0] - end[0]) / 2.0
	dy2 = (start[1] - end[1]) / 2.0
	x1 = cos_a * dx2 + sin_a * dy2
	y1 = -sin_a * dx2 + cos_a * dy2

	overshoot = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
	if overshoot > 1.0:
		rx *= math.sqrt(overshoot)
		ry *= math.sqrt(overshoot)

	numerator = max(0.0, rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1)
	denominator = rx * rx * y1 * y1 + ry * ry * x1 * x1
	factor = math.sqrt(numerator / denominator) if denominator else 0.0
	if large_arc == sweep:
		factor = -factor
	cx1 = factor * rx * y1 / ry
	cy1 = -factor * ry * x1 / rx
	center_x = cos_a * cx1 - sin_a * cy1 + (start[0] + end[0]) / 2.0
	center_y = sin_a * cx1 + cos_a * cy1 + (start[1] + end[1]) / 2.0

	start_angle = math.atan2((y1 - cy1) / ry, (x1 - cx1) / rx)
	end_angle = math.atan2((-y1 - cy1) / ry, (-x1 - cx1) / rx)
	delta = end_angle - start_angle
	if sweep and delta < 0.0:
		delta += 2.0 * math.pi
	elif not sweep and delta > 0.0:
		delta -= 2.0 * math.pi

	points = []
	for step in range(1, ARC_SEGMENTS + 1):
		theta = start_angle + delta * step / ARC_SEGMENTS
		x = rx * math.cos(theta)
		y = ry * math.sin(theta)
		points.append((cos_a * x - sin_a * y + center_x, sin_a * x + cos_a * y + center_y))
	return points


def flatten_path(data: str) -> list[list[tuple[float, float]]]:
	"""Return the subpaths of an SVG path, with curves sampled as line segments.

	Supports the commands the two marks use: move, line, horizontal and vertical
	line, cubic and smooth cubic curve, elliptical arc, and close.

	Args:
		data: The path data of an SVG "d" attribute. str, non-empty.

	Returns:
		list of list of tuple[float, float]: One point list per subpath, in path
		order.
	"""
	reader = _PathReader(data)
	subpaths: list[list[tuple[float, float]]] = []
	current_points: list[tuple[float, float]] = []
	current = (0.0, 0.0)
	start_of_subpath = (0.0, 0.0)
	previous_control: tuple[float, float] | None = None
	command = ""

	while not reader.done:
		letter = reader.command()
		if letter is not None:
			if letter not in SUPPORTED_COMMANDS:
				raise ValueError(f"Unsupported path command {letter!r}")
			command = letter
		upper = command.upper()
		origin = current if command.islower() else (0.0, 0.0)

		if upper == "Z":
			if current_points:
				subpaths.append(current_points)
				current_points = []
			current = start_of_subpath
			previous_control = None
			continue

		if upper == "M":
			if current_points:
				subpaths.append(current_points)
			current = reader.point(origin)
			start_of_subpath = current
			current_points = [current]
			previous_control = None
			# A second pair after a move is an implicit line, which the SVG
			# specification defines by switching the command rather than the letter.
			command = "l" if command == "m" else "L"
			continue

		if upper == "L":
			current = reader.point(origin)
		elif upper == "H":
			current = (origin[0] + reader.number(), current[1])
		elif upper == "V":
			current = (current[0], origin[1] + reader.number())
		elif upper in ("C", "S"):
			if upper == "C":
				first = reader.point(origin)
			else:
				first = current if previous_control is None else (
					2.0 * current[0] - previous_control[0],
					2.0 * current[1] - previous_control[1],
				)
			second = reader.point(origin)
			end = reader.point(origin)
			current_points.extend(cubic_points(current, first, second, end, CURVE_SEGMENTS))
			previous_control = second
			current = end
			continue
		else:
			radii = (reader.number(), reader.number())
			rotation = reader.number()
			large_arc, sweep = reader.flag(), reader.flag()
			end = reader.point(origin)
			current_points.extend(_arc_points(current, end, radii, rotation, large_arc, sweep))
			previous_control = None
			current = end
			continue

		previous_control = None
		current_points.append(current)

	if current_points:
		subpaths.append(current_points)
	return subpaths


@lru_cache(maxsize=8)
def logo_subpaths(file_name: str, size: int) -> tuple[tuple[tuple[float, float], ...], ...]:
	"""Return a provider mark as polygons, scaled to fit a square of a given size.

	The mark is filled under the even odd rule, so the subpaths are returned as
	they were read rather than merged: a caller that fills them all at once with
	that rule gets the holes, and a caller that fills them one at a time does
	not.

	Results are cached because a surface asks for the same mark on every redraw.

	Args:
		file_name: Name of the SVG inside the assets directory, such as
			"claude.svg". str, non-empty.
		size: Edge length of the square the mark is fitted into, in the caller's
			own units. int, greater than 0.

	Returns:
		tuple of tuple of tuple[float, float]: One point list per subpath, in
		path order, with x to the right and y downward from the top left corner
		of that square.

	Raises:
		ValueError: When the file carries no path data or no view box.
	"""
	require_non_empty_str(file_name, "file_name")
	require_positive_int(size, "size")

	source = ASSETS_DIR / file_name
	markup = source.read_text(encoding="utf-8")
	view_box = VIEW_BOX_PATTERN.search(markup)
	paths = PATH_DATA_PATTERN.findall(markup)
	if not paths or view_box is None:
		raise ValueError(f"{source} has no path data or no view box")

	min_x, min_y, width, height = (float(value) for value in view_box.group(1).split())
	scale = size / max(width, height)
	return tuple(
		tuple(((x - min_x) * scale, (y - min_y) * scale) for x, y in points)
		for data in paths
		for points in flatten_path(data)
	)
