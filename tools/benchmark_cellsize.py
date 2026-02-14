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
from tools.run_demo import build_demo_case


def _load_esri_ascii_module():
    module_path = PROJECT_ROOT / "io" / "esri_ascii.py"
    spec = importlib.util.spec_from_file_location("local_esri_ascii", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    esri_ascii = _load_esri_ascii_module()
    base_case = build_demo_case()

    for cellsize in (50.0, 25.0, 10.0):
        case = dict(base_case)
        case["grid"] = dict(base_case["grid"])
        case["grid"]["cellsize_m"] = cellsize

        t0 = time.perf_counter()
        hours, header = run_annual_shadow_hours(case)
        elapsed_s = time.perf_counter() - t0

        out_path = PROJECT_ROOT / "outputs" / f"benchmark_shadow_{int(cellsize)}m.asc"
        esri_ascii.write_esri_ascii(
            path=out_path,
            data=hours,
            xllcorner=float(header["xllcorner"]),
            yllcorner=float(header["yllcorner"]),
            cellsize=float(header["cellsize"]),
            nodata=float(header["nodata"]),
        )

        shaded = int(np.count_nonzero(hours > 0))
        print(f"\nCellsize: {cellsize:.0f} m")
        print(f"Output: {out_path}")
        print(f"Tempo esecuzione [s]: {elapsed_s:.3f}")
        print(f"Min ore: {hours.min():.3f}")
        print(f"Max ore: {hours.max():.3f}")
        print(f"Mean ore: {hours.mean():.3f}")
        print(f"Celle ombreggiate (>0): {shaded}")


if __name__ == "__main__":
    main()