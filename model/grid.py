from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GridSpec:
    bbox: tuple[float, float, float, float]
    cellsize_m: float
    nodata: float = -9999.0


def _grid_shape(spec: GridSpec) -> tuple[int, int]:
    xmin, ymin, xmax, ymax = spec.bbox
    if spec.cellsize_m <= 0:
        raise ValueError("cellsize_m must be > 0")
    if xmax <= xmin or ymax <= ymin:
        raise ValueError("Invalid bbox: expected xmax>xmin and ymax>ymin")

    width_cells = (xmax - xmin) / spec.cellsize_m
    height_cells = (ymax - ymin) / spec.cellsize_m

    ncols = int(round(width_cells))
    nrows = int(round(height_cells))

    if not np.isclose(width_cells, ncols) or not np.isclose(height_cells, nrows):
        raise ValueError("bbox extents must be multiples of cellsize_m")

    return nrows, ncols


def build_grid(
    spec: GridSpec,
) -> tuple[np.ndarray, np.ndarray, int, int, float, float]:
    """Build cell-center coordinates and ESRI ASCII header corner values."""
    xmin, ymin, xmax, ymax = spec.bbox
    nrows, ncols = _grid_shape(spec)

    half = spec.cellsize_m / 2.0
    xs = xmin + half + np.arange(ncols, dtype=np.float64) * spec.cellsize_m
    # Row 0 is top row in memory and in ESRI first written line.
    ys = ymax - half - np.arange(nrows, dtype=np.float64) * spec.cellsize_m

    return xs, ys, ncols, nrows, xmin, ymin


def world_to_index(x: float, y: float, spec: GridSpec) -> tuple[int, int]:
    """Map world coordinates to (row, col), with row=0 at the top."""
    xmin, _ymin, _xmax, ymax = spec.bbox
    col = int(np.floor((x - xmin) / spec.cellsize_m))
    row = int(np.floor((ymax - y) / spec.cellsize_m))
    return row, col