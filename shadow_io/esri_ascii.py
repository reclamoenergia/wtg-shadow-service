from __future__ import annotations

from pathlib import Path

import numpy as np


def write_esri_ascii(
    path: str | Path,
    data: np.ndarray,
    xllcorner: float,
    yllcorner: float,
    cellsize: float,
    nodata: float,
) -> None:
    """Write a raster array to ESRI ASCII Grid format."""
    if data.ndim != 2:
        raise ValueError("data must be a 2D array [nrows, ncols]")

    nrows, ncols = data.shape
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    header = [
        f"ncols {ncols}",
        f"nrows {nrows}",
        f"xllcorner {xllcorner}",
        f"yllcorner {yllcorner}",
        f"cellsize {cellsize}",
        f"NODATA_value {nodata}",
    ]

    with path.open("w", encoding="utf-8") as f:
        f.write("\n".join(header))
        f.write("\n")
        for row in data:
            f.write(" ".join(f"{float(v):.6f}" for v in row))
            f.write("\n")


def read_esri_ascii(path: str | Path) -> tuple[np.ndarray, dict[str, float | int]]:
    """Read an ESRI ASCII Grid file and return data + parsed header."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        header_lines = [next(f).strip() for _ in range(6)]
        body_lines = [line.strip() for line in f if line.strip()]

    header: dict[str, float | int] = {}
    for line in header_lines:
        key, value = line.split(maxsplit=1)
        key_l = key.lower()
        if key_l in {"ncols", "nrows"}:
            header[key_l] = int(float(value))
        else:
            header[key_l] = float(value)

    nrows = int(header["nrows"])
    ncols = int(header["ncols"])

    data = np.array(
        [[float(v) for v in line.split()] for line in body_lines],
        dtype=np.float32,
    )

    if data.shape != (nrows, ncols):
        raise ValueError(f"Data shape {data.shape} does not match header {(nrows, ncols)}")

    return data, header