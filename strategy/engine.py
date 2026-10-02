"""Strategy engine — professional SMC H1/M5 (assembled from _engine_parts)."""
from __future__ import annotations
from pathlib import Path as _Path

_parts_dir = _Path(__file__).resolve().parent / "_engine_parts"
_n = len(list(_parts_dir.glob("part_*.txt")))
_src = "".join((_parts_dir / f"part_{i:02d}.txt").read_text() for i in range(_n))
exec(compile(_src, str(_Path(__file__).resolve()), "exec"), globals())
