from __future__ import annotations

import numpy as np

from model.grid import GridSpec, build_grid, world_to_index
from model.solar import build_times_for_year, filter_daylight, solar_position


def shadow_ellipse_params(
    hub_height_m: float,
    rotor_radius_m: float,
    elev_rad: float,
) -> tuple[float, float, float]:
    """Return major axis a, minor axis b, and center offset d."""
    if elev_rad <= 0.0:
        raise ValueError("elev_rad must be > 0")

    H = hub_height_m
    R = rotor_radius_m

    L1 = (H + R) / np.tan(elev_rad)  # Excel: (H+R)*cot(e)
    a = 0.5 * L1  # semi-asse maggiore
    b = R  # semi-asse minore
    d_center = a  # centro ellisse a distanza a
    return float(a), float(b), float(d_center)


def shadow_center(x0: float, y0: float, d: float, az_rad: float) -> tuple[float, float]:
    """Shadow center from turbine hub projected opposite to sun azimuth."""
    xc = x0 - d * np.sin(az_rad)
    yc = y0 - d * np.cos(az_rad)
    return float(xc), float(yc)


def _bbox_to_block(
    spec: GridSpec,
    xs: np.ndarray,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
) -> tuple[int, int, int, int]:
    ncols = xs.size
    nrows = int(round((spec.bbox[3] - spec.bbox[1]) / spec.cellsize_m))

    col0 = int(np.searchsorted(xs, xmin, side="left"))
    col1 = int(np.searchsorted(xs, xmax, side="right"))

    row0, _ = world_to_index(spec.bbox[0], ymax, spec)
    row1, _ = world_to_index(spec.bbox[0], ymin, spec)
    row1 += 1

    col0 = max(0, min(ncols, col0))
    col1 = max(0, min(ncols, col1))
    row0 = max(0, min(nrows, row0))
    row1 = max(0, min(nrows, row1))

    return row0, row1, col0, col1


def apply_turbine_shadow_to_mask(
    mask: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    spec: GridSpec,
    x0: float,
    y0: float,
    hub_height: float,
    rotor_radius: float,
    elev_deg: float,
    az_deg: float,
) -> None:
    elev_rad = float(np.deg2rad(elev_deg))
    az_rad = float(np.deg2rad(az_deg))

    if elev_rad <= 0.0:
        return

    a, b, d_center = shadow_ellipse_params(
        hub_height_m=hub_height,
        rotor_radius_m=rotor_radius,
        elev_rad=elev_rad,
    )
    xc, yc = shadow_center(x0=x0, y0=y0, d=d_center, az_rad=az_rad)

    xmin = xc - a
    xmax = xc + a
    ymin = yc - a
    ymax = yc + a

    row0, row1, col0, col1 = _bbox_to_block(spec, xs, xmin, xmax, ymin, ymax)
    if row1 <= row0 or col1 <= col0:
        return

    block_xs = xs[col0:col1]
    block_ys = ys[row0:row1]
    xx, yy = np.meshgrid(block_xs, block_ys, indexing="xy")

    dx = xx - xc
    dy = yy - yc

    u = dx * np.sin(az_rad) + dy * np.cos(az_rad)
    v = dx * np.cos(az_rad) - dy * np.sin(az_rad)

    block_mask = (u / a) ** 2 + (v / b) ** 2 <= 1.0
    mask[row0:row1, col0:col1] |= block_mask


def run_annual_shadow_hours(case: dict) -> tuple[np.ndarray, dict[str, float | int]]:
    site = case["site"]
    grid = case["grid"]
    turbines = case["turbines"]

    min_elevation_deg = float(case.get("min_elevation_deg", 0.0))
    dt_hours = 0.25

    spec = GridSpec(
        bbox=tuple(grid["bbox"]),
        cellsize_m=float(grid["cellsize_m"]),
        nodata=float(grid.get("nodata", -9999.0)),
    )

    xs, ys, ncols, nrows, xllcorner, yllcorner = build_grid(spec)
    hours = np.zeros((nrows, ncols), dtype=np.float32)

    times = build_times_for_year(
        year=int(site["year"]),
        timezone=str(site["timezone"]),
        step_minutes=15,
    )
    pos = solar_position(
        times=times,
        latitude_deg=float(site["latitude_deg"]),
        longitude_deg=float(site["longitude_deg"]),
    )
    daylight = filter_daylight(pos, min_elevation_deg=min_elevation_deg)
    print("Timestep totali:", len(pos))
    print("Timestep diurni:", len(daylight))
    print("Ore massime teoriche:", len(daylight) * 0.25)



    for elev_deg, az_deg in daylight[["apparent_elevation", "azimuth"]].itertuples(index=False, name=None):
        mask = np.zeros((nrows, ncols), dtype=bool)

        for turb in turbines:
            apply_turbine_shadow_to_mask(
                mask=mask,
                xs=xs,
                ys=ys,
                spec=spec,
                x0=float(turb["x"]),
                y0=float(turb["y"]),
                hub_height=float(turb["hub_height_m"]),
                rotor_radius=float(turb["rotor_diameter_m"]) / 2.0,
                elev_deg=float(elev_deg),
                az_deg=float(az_deg),
            )

        hours[mask] += dt_hours

    header: dict[str, float | int] = {
        "ncols": ncols,
        "nrows": nrows,
        "xllcorner": xllcorner,
        "yllcorner": yllcorner,
        "cellsize": spec.cellsize_m,
        "nodata": spec.nodata,
    }
    return hours, header
