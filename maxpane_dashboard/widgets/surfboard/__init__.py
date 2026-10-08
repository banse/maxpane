"""Render-only SURFBOARD hub widgets sharing the existing SURF data contract."""
from .rack import SurfboardRack
from .terminal import SurfboardTerminal

__all__ = ["SurfboardRack", "SurfboardTerminal"]
