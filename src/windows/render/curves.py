"""Sample parametric curves as point lists.

Both the provider marks and the plan flames are outlines described by cubic
Bezier segments, and neither Pillow nor the Tk canvas takes a curve directly, so
each segment is flattened here into the points a polygon is drawn from.
"""

from __future__ import annotations

from ..validation import require_positive_int, require_type

Point = tuple[float, float]


def cubic_points(start: Point, first: Point, second: Point, end: Point, steps: int) -> list[Point]:
	"""Flatten a cubic Bezier curve into a list of points.

	Args:
		start: Where the curve begins as (x, y). tuple of two floats.
		first: The control point leaving the start as (x, y). tuple of two floats.
		second: The control point entering the end as (x, y). tuple of two floats.
		end: Where the curve ends as (x, y). tuple of two floats.
		steps: How many segments to sample the curve into. int, greater than 0.

	Returns:
		list of tuple[float, float]: The sampled points, excluding the start and
		including the end.
	"""
	for name, point in (("start", start), ("first", first), ("second", second), ("end", end)):
		require_type(point, tuple, name)
	require_positive_int(steps, "steps")

	points: list[Point] = []
	for step in range(1, steps + 1):
		t = step / steps
		u = 1.0 - t
		points.append(
			(
				u * u * u * start[0] + 3 * u * u * t * first[0] + 3 * u * t * t * second[0] + t * t * t * end[0],
				u * u * u * start[1] + 3 * u * u * t * first[1] + 3 * u * t * t * second[1] + t * t * t * end[1],
			)
		)
	return points
