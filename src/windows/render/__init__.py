"""Reading marks, and drawing for Windows.

Two different things live here. svg.py reads a provider mark out of its SVG as
plain polygons and imports no drawing library at all, so the outline can be
filled by whatever is drawing. Everything else draws with Pillow: the
notification area icon, the mark as a bitmap, and the palette and type ramp the
panel is set in.
"""
