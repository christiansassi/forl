"""Rasterize a provider mark for the Windows panel.

The polygons come from svg.py, which reads them out of the SVG without needing a
drawing library. They are combined here under the even odd rule, which is what
makes the holes in the OpenAI knot holes rather than solid, and filled on a
supersampled canvas that is reduced at the end, which keeps the edges of the
mark smooth at the sizes the panel uses.
"""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw

from ..validation import require_non_empty_str, require_positive_int
from .svg import logo_subpaths
from .theme import TRANSPARENT

SUPERSAMPLE = 4


def _even_odd_mask(subpaths: tuple[tuple[tuple[float, float], ...], ...], size: int) -> Image.Image:
	"""Combine flattened subpaths into one coverage mask under the even odd rule.

	Each subpath is filled on its own and the results are combined with exclusive
	or, so a region covered an even number of times ends up empty. That is what
	turns the overlaps of a knot into holes.

	Args:
		subpaths: The point lists to fill. tuple of tuple of tuple[float, float].
		size: Edge length of the square mask in pixels. int, greater than 0.

	Returns:
		PIL.Image.Image: The mask, mode "1", size by size pixels.
	"""
	mask = Image.new("1", (size, size), 0)
	for points in subpaths:
		if len(points) < 3:
			continue
		layer = Image.new("1", (size, size), 0)
		ImageDraw.Draw(layer).polygon(list(points), fill=1)
		mask = ImageChops.logical_xor(mask, layer)
	return mask


@lru_cache(maxsize=8)
def render_logo(file_name: str, size: int, color: str) -> Image.Image:
	"""Render a provider mark as a square RGBA image with a transparent background.

	Results are cached because the panel asks for the same mark on every rebuild.

	Args:
		file_name: Name of the SVG inside the assets directory, such as
			"claude.svg". str, non-empty.
		size: Width and height of the returned image in pixels. int, greater than 0.
		color: Fill color as a "#rrggbb" string. str, non-empty.

	Returns:
		PIL.Image.Image: The rendered mark, mode "RGBA", size by size pixels.
	"""
	require_non_empty_str(file_name, "file_name")
	require_positive_int(size, "size")
	require_non_empty_str(color, "color")

	canvas_size = size * SUPERSAMPLE
	mask = _even_odd_mask(logo_subpaths(file_name, canvas_size), canvas_size)

	image = Image.new("RGBA", (canvas_size, canvas_size), TRANSPARENT)
	image.paste(Image.new("RGBA", (canvas_size, canvas_size), color), mask=mask)
	return image.resize((size, size), Image.LANCZOS)
