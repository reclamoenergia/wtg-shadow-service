from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from model.shadow import run_annual_shadow_hours
from shadow_io.esri_ascii import write_esri_ascii

app = FastAPI(title="WTG Shadow Service")

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health():
    return {"status": "ok"}


class Site(BaseModel):
    latitude: float
    longitude: float
    timezone: str = "Europe/Rome"
    year: int


class Grid(BaseModel):
    cellsize_m: float = 20.0
    bbox: Optional[List[float]] = None  # [xmin, ymin, xmax, ymax]
    buffer_m: Optional[float] = 5000.0
    nodata: float = -9999.0


class Turbine(BaseModel):
    id: str
    x: float
    y: float
    hub_height_m: float
    rotor_diameter_m: float


class Simulation(BaseModel):
    min_solar_elevation_deg: float = 0.0


class SimulationRequest(BaseModel):
    site: Site
    grid: Grid
    turbines: List[Turbine]
    simulation: Simulation = Field(default_factory=Simulation)


def _bbox_from_turbines(turbines: List[Turbine], buffer_m: float) -> List[float]:
    xs = [t.x for t in turbines]
    ys = [t.y for t in turbines]
    xmin = min(xs) - buffer_m
    xmax = max(xs) + buffer_m
    ymin = min(ys) - buffer_m
    ymax = max(ys) + buffer_m
    return [xmin, ymin, xmax, ymax]


def _safe_output_filename(name: str) -> str:
    # basic hardening: only filename, no paths
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError("Invalid filename")
    if not name.lower().endswith(".asc"):
        raise ValueError("Only .asc files allowed")
    return name


@app.post("/simulate")
def simulate(req: SimulationRequest):
    if not req.turbines:
        raise HTTPException(status_code=400, detail="turbines list is empty")

    bbox = req.grid.bbox
    if bbox is None:
        buffer_m = float(req.grid.buffer_m or 5000.0)
        bbox = _bbox_from_turbines(req.turbines, buffer_m)

    case = {
        "site": {
            "latitude_deg": req.site.latitude,
            "longitude_deg": req.site.longitude,
            "timezone": req.site.timezone,
            "year": req.site.year,
        },
        "grid": {
            "bbox": tuple(bbox),
            "cellsize_m": float(req.grid.cellsize_m),
            "nodata": float(req.grid.nodata),
        },
        "turbines": [
            {
                "id": t.id,
                "x": float(t.x),
                "y": float(t.y),
                "hub_height_m": float(t.hub_height_m),
                "rotor_diameter_m": float(t.rotor_diameter_m),
            }
            for t in req.turbines
        ],
        "simulation": {"min_solar_elevation_deg": float(req.simulation.min_solar_elevation_deg)},
    }

    hours, header = run_annual_shadow_hours(case)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"shadow_hours_{ts}.asc"
    out_path = OUTPUT_DIR / filename

    write_esri_ascii(
        out_path,
        hours,
        xllcorner=float(header["xllcorner"]),
        yllcorner=float(header["yllcorner"]),
        cellsize=float(header["cellsize"]),
        nodata=float(header["nodata"]),
    )

    return {
        "status": "done",
        "filename": filename,
        "download_url": f"/results/{filename}",
        "max": float(np.max(hours)),
        "mean": float(np.mean(hours)),
    }


@app.get("/results/{filename}")
def download_result(filename: str):
    try:
        safe = _safe_output_filename(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = OUTPUT_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path, media_type="text/plain", filename=safe)
