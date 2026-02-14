from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.shadow import run_annual_shadow_hours


def _load_esri_ascii_module():
    module_path = PROJECT_ROOT / "io" / "esri_ascii.py"
    spec = importlib.util.spec_from_file_location("local_esri_ascii", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_demo_case() -> dict:
    turbines = [
        {
            "id": "T01",
            "x": 552451,
            "y": 4553186,
            "hub_height_m": 114,
            "rotor_diameter_m": 172,
        },
        {
            "id": "T02",
            "x": 552917,
            "y": 4553488,
            "hub_height_m": 114,
            "rotor_diameter_m": 172,
        },
        {
            "id": "T03",
            "x": 553217,
            "y": 4552799,
            "hub_height_m": 114,
            "rotor_diameter_m": 172,
        },
        {
            "id": "T04",
            "x": 553454,
            "y": 4552182,
            "hub_height_m": 114,
            "rotor_diameter_m": 172,
        },
        {
            "id": "T05",
            "x": 554046,
            "y": 4552428,
            "hub_height_m": 114,
            "rotor_diameter_m": 172,
        },
        {
            "id": "T06",
            "x": 554253,
            "y": 4552909,
            "hub_height_m": 114,
            "rotor_diameter_m": 172,
        },
    ]

    margin_m = 2500.0
    cellsize_m = 20.0
    xs = [float(t["x"]) for t in turbines]
    ys = [float(t["y"]) for t in turbines]
    xmin_raw = min(xs) - margin_m
    ymin_raw = min(ys) - margin_m
    xmax_raw = max(xs) + margin_m
    ymax_raw = max(ys) + margin_m
    bbox = (
        np.floor(xmin_raw / cellsize_m) * cellsize_m,
        np.floor(ymin_raw / cellsize_m) * cellsize_m,
        np.ceil(xmax_raw / cellsize_m) * cellsize_m,
        np.ceil(ymax_raw / cellsize_m) * cellsize_m,
    )

    return {
        "site": {
            "latitude_deg": 41.12,
            "longitude_deg": 16.8719,
            "timezone": "Europe/Rome",
            "year": 2026,
        },
        "grid": {
            "bbox": bbox,
            "cellsize_m": cellsize_m,
            "nodata": -9999.0,
        },
        "turbines": turbines,
        "min_elevation_deg": 10.0,
    }


def main() -> None:
    esri_ascii = _load_esri_ascii_module()
    case = build_demo_case()

    t0 = time.perf_counter()
    hours, header = run_annual_shadow_hours(case)
    elapsed_s = time.perf_counter() - t0

    out_path = PROJECT_ROOT / "outputs" / "demo_shadow_hours.asc"
    esri_ascii.write_esri_ascii(
        path=out_path,
        data=hours,
        xllcorner=float(header["xllcorner"]),
        yllcorner=float(header["yllcorner"]),
        cellsize=float(header["cellsize"]),
        nodata=float(header["nodata"]),
    )

    shaded = int(np.count_nonzero(hours > 0))
    print(f"Output: {out_path}")
    print(f"Tempo esecuzione [s]: {elapsed_s:.3f}")
    print(f"Min ore: {hours.min():.3f}")
    print(f"Max ore: {hours.max():.3f}")
    print(f"Mean ore: {hours.mean():.3f}")
    print(f"Celle ombreggiate (>0): {shaded}")


if __name__ == "__main__":
    main()
