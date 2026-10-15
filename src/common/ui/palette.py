"""The palette the popups are drawn in right now.

The two palettes live with the rest of the theme, and the question of which app
mode the user chose is the system backend's to answer. The panel and the menu
both need the two put together, each time they open, so it is done here once.
"""

from __future__ import annotations

from ..render.theme import DARK_PALETTE, LIGHT_PALETTE, Palette
from ..system import uses_light_theme


def current_palette() -> Palette:
	"""Return the palette of the app mode the user has chosen.

	Asked each time a popup opens rather than once at launch, so a popup opened
	after the user changes the mode in Settings follows the change.

	Returns:
		Palette: LIGHT_PALETTE in the light mode, DARK_PALETTE otherwise.
	"""
	return LIGHT_PALETTE if uses_light_theme() else DARK_PALETTE
