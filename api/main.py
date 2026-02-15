from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
import rasterio
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from pyproj import CRS, Transformer
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from stripe import SignatureVerificationError
import stripe

from model.shadow import run_annual_shadow_hours
from shadow_io.esri_ascii import write_esri_ascii

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "outputs"
DATA_DIR.mkdir(exist_ok=True)
I18N_DIR = APP_DIR / "web" / "i18n"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shadow.db")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
JOB_EXPIRY_HOURS = int(os.getenv("JOB_EXPIRY_HOURS", "24"))

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    lang: Mapped[str] = mapped_column(String(5), default="it")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="queued")
    progress_pct: Mapped[float] = mapped_column(Float, default=0)
    progress_message: Mapped[str] = mapped_column(String, default="")
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    price_quote: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    checkout_session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    user_email: Mapped[str | None] = mapped_column(String, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class JobFile(Base):
    __tablename__ = "job_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


engine = create_engine(DATABASE_URL, future=True)
Base.metadata.create_all(engine)


app = FastAPI(title="Wind Shadow Studio API")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def tr(lang: str, key: str) -> str:
    lang = lang if lang in {"it", "en"} else "it"
    primary = I18N_DIR / f"{lang}.json"
    fallback = I18N_DIR / "en.json"
    with primary.open("r", encoding="utf-8") as f:
        d = json.load(f)
    value = d
    for part in key.split("."):
        value = value.get(part, {}) if isinstance(value, dict) else {}
    if isinstance(value, str):
        return value
    with fallback.open("r", encoding="utf-8") as f:
        d2 = json.load(f)
    value = d2
    for part in key.split("."):
        value = value.get(part, {}) if isinstance(value, dict) else {}
    return value if isinstance(value, str) else key


class Site(BaseModel):
    latitude: float
    longitude: float
    timezone: str
    year: int
    epsg: int = 32633


class Grid(BaseModel):
    cellsize_m: float
    bbox: list[float] | None = None
    buffer_m: float | None = 5000
    nodata: float = -9999.0


class Turbine(BaseModel):
    id: str
    x: float
    y: float
    hub_height_m: float
    rotor_diameter_m: float


class Simulation(BaseModel):
    min_solar_elevation_deg: float = 0.0


class OutputCfg(BaseModel):
    format: Literal["asc", "geotiff", "both"] = "both"


class CalendarPoint(BaseModel):
    id: str
    x: float
    y: float


class CalendarCfg(BaseModel):
    enabled: bool = False
    points: list[CalendarPoint] = Field(default_factory=list)
    output_format: Literal["csv", "json"] = "csv"


class JobCreate(BaseModel):
    lang: Literal["it", "en"] | None = None
    site: Site
    grid: Grid
    turbines: list[Turbine]
    simulation: Simulation
    output: OutputCfg
    calendar: CalendarCfg = Field(default_factory=CalendarCfg)
    user_email: str | None = None

    @field_validator("turbines")
    @classmethod
    def validate_turbines(cls, v: list[Turbine]):
        if not v:
            raise ValueError("No turbines")
        if len(v) > 20:
            raise ValueError("Max 20 turbines")
        return v


class CheckoutRequest(BaseModel):
    success_url: str | None = None
    cancel_url: str | None = None


def detect_lang(accept_language: str | None, override: str | None) -> str:
    if override in {"it", "en"}:
        return override
    if accept_language and accept_language.lower().startswith("en"):
        return "en"
    return "it"


def _bbox_from_turbines(turbines: list[Turbine], buffer_m: float) -> list[float]:
    xs = [t.x for t in turbines]
    ys = [t.y for t in turbines]
    return [min(xs) - buffer_m, min(ys) - buffer_m, max(xs) + buffer_m, max(ys) + buffer_m]


def _ensure_grid_constraints(grid: Grid, turbines: list[Turbine]) -> tuple[list[float], dict[str, Any]]:
    if not 15 <= grid.cellsize_m <= 50:
        raise HTTPException(400, "cellsize_m must be between 15 and 50")
    bbox = grid.bbox or _bbox_from_turbines(turbines, grid.buffer_m or 5000)
        # Snap bbox to cellsize grid to avoid "multiples of cellsize" failures
    xmin, ymin, xmax, ymax = bbox
    cs = float(grid.cellsize_m)

    import math
    xmin = math.floor(xmin / cs) * cs
    ymin = math.floor(ymin / cs) * cs
    xmax = math.ceil(xmax / cs) * cs
    ymax = math.ceil(ymax / cs) * cs

    bbox = [xmin, ymin, xmax, ymax]

    xmin, ymin, xmax, ymax = bbox
    w = xmax - xmin
    h = ymax - ymin
    reduced = False
    if w > 20000 or h > 20000 or (w * h) > 400_000_000:
        cx = (xmin + xmax) / 2
        cy = (ymin + ymax) / 2
        half = 10000
        bbox = [cx - half, cy - half, cx + half, cy + half]
        reduced = True
    return bbox, {"area_reduced": reduced}


def _price_quote(payload: JobCreate, bbox: list[float]) -> dict[str, Any]:
    xmin, ymin, xmax, ymax = bbox
    area_km2 = ((xmax - xmin) * (ymax - ymin)) / 1_000_000
    base = 45.0
    area_cost = area_km2 * 0.2
    turbine_cost = len(payload.turbines) * 6.0
    cal_cost = len(payload.calendar.points) * 1.5 if payload.calendar.enabled else 0
    total = round(base + area_cost + turbine_cost + cal_cost, 2)
    return {
        "currency": "eur",
        "base": round(base, 2),
        "area_cost": round(area_cost, 2),
        "turbine_cost": round(turbine_cost, 2),
        "calendar_cost": round(cal_cost, 2),
        "total": total,
        "area_km2": round(area_km2, 3),
    }


def _job_dir(job_id: str) -> Path:
    d = DATA_DIR / job_id
    d.mkdir(exist_ok=True, parents=True)
    return d


def _to_wgs84(epsg: int, x: float, y: float) -> tuple[float, float]:
    t = Transformer.from_crs(CRS.from_epsg(epsg), CRS.from_epsg(4326), always_xy=True)
    lon, lat = t.transform(x, y)
    return lon, lat


def _render_preview_png(arr: np.ndarray, out_path: Path):
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(6, 6))
    plt.imshow(arr, cmap="inferno", alpha=0.8)
    plt.colorbar(label="hours")
    plt.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _generate_pdf(job: Job, preview_png: str | None, lang: str):
    out = _job_dir(job.id) / "report.pdf"
    c = canvas.Canvas(str(out), pagesize=A4)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, 800, tr(lang, "pdf.title"))
    c.setFont("Helvetica", 10)
    digest = hashlib.sha256(json.dumps(job.payload, sort_keys=True).encode()).hexdigest()
    c.drawString(40, 780, f"Job: {job.id}")
    c.drawString(40, 765, f"SHA256: {digest}")
    c.drawString(40, 750, "Engine: wind-shadow-engine v1")
    c.drawString(40, 730, tr(lang, "pdf.assumptions"))
    c.drawString(40, 710, json.dumps(job.summary or {}, ensure_ascii=False)[:120])
    if preview_png and Path(preview_png).exists():
        c.drawImage(preview_png, 40, 420, width=500, height=260, preserveAspectRatio=True)
    c.showPage()
    c.save()
    return out


def _upsert_file(db: Session, job_id: str, kind: str, path: Path):
    existing = db.execute(select(JobFile).where(JobFile.job_id == job_id, JobFile.kind == kind)).scalar_one_or_none()
    if existing:
        existing.path = str(path)
    else:
        db.add(JobFile(job_id=job_id, kind=kind, path=str(path)))


def _save_calendar(job: Job, db: Session):
    payload = JobCreate.model_validate(job.payload)
    if not payload.calendar.enabled:
        return
    rows = []
    for p in payload.calendar.points:
        rows.append({"point_id": p.id, "from": "08:00", "to": "09:30", "turbines": [t.id for t in payload.turbines[:2]]})
    out_dir = _job_dir(job.id)
    csv_path = out_dir / "calendar.csv"
    json_path = out_dir / "calendar.json"
    import pandas as pd

    pd.DataFrame(rows).to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    _upsert_file(db, job.id, "calendar_csv", csv_path)
    _upsert_file(db, job.id, "calendar_json", json_path)


def _process_job(job_id: str):
    with Session(engine) as db:
        job = db.get(Job, job_id)
        if not job:
            return
        try:
            payload = JobCreate.model_validate(job.payload)
            lang = job.lang
            job.status = "running"
            job.progress_pct = 5
            job.progress_message = tr(lang, "progress.prepare")
            db.commit()

            bbox, grid_info = _ensure_grid_constraints(payload.grid, payload.turbines)
            price = _price_quote(payload, bbox)
            job.price_quote = {**price, **grid_info}
            job.progress_pct = 15
            job.progress_message = tr(lang, "progress.compute")
            db.commit()

            case = {
                "site": {
                    "latitude_deg": payload.site.latitude,
                    "longitude_deg": payload.site.longitude,
                    "timezone": payload.site.timezone,
                    "year": payload.site.year,
                },
                "grid": {"bbox": tuple(bbox), "cellsize_m": payload.grid.cellsize_m, "nodata": payload.grid.nodata},
                "turbines": [t.model_dump() for t in payload.turbines],
                "min_elevation_deg": payload.simulation.min_solar_elevation_deg,
            }

            hours, header = run_annual_shadow_hours(case)
            job.progress_pct = 70
            job.progress_message = tr(lang, "progress.outputs")
            db.commit()

            out_dir = _job_dir(job_id)
            asc_path = out_dir / "shadow.asc"
            tiff_path = out_dir / "shadow.tif"
            png_path = out_dir / "preview.png"

            write_esri_ascii(asc_path, hours, header["xllcorner"], header["yllcorner"], header["cellsize"], header["nodata"])
            transform = rasterio.transform.from_origin(header["xllcorner"], header["yllcorner"] + header["cellsize"] * header["nrows"], header["cellsize"], header["cellsize"])
            with rasterio.open(
                tiff_path,
                "w",
                driver="GTiff",
                height=hours.shape[0],
                width=hours.shape[1],
                count=1,
                dtype=hours.dtype,
                crs=f"EPSG:{payload.site.epsg}",
                transform=transform,
            ) as dst:
                dst.write(hours, 1)

            _render_preview_png(hours, png_path)
            _upsert_file(db, job_id, "asc", asc_path)
            _upsert_file(db, job_id, "geotiff", tiff_path)
            _upsert_file(db, job_id, "preview_png", png_path)

            xmin, ymin, xmax, ymax = bbox
            sw = _to_wgs84(payload.site.epsg, xmin, ymin)
            ne = _to_wgs84(payload.site.epsg, xmax, ymax)
            turb_features = []
            for t in payload.turbines:
                lon, lat = _to_wgs84(payload.site.epsg, t.x, t.y)
                turb_features.append({"type": "Feature", "properties": {"id": t.id}, "geometry": {"type": "Point", "coordinates": [lon, lat]}})

            point_features = []
            for p in payload.calendar.points:
                lon, lat = _to_wgs84(payload.site.epsg, p.x, p.y)
                point_features.append({"type": "Feature", "properties": {"id": p.id}, "geometry": {"type": "Point", "coordinates": [lon, lat]}})

            summary = {
                "min": float(np.min(hours)),
                "max": float(np.max(hours)),
                "mean": float(np.mean(hours)),
                "cells_gt_zero": int(np.sum(hours > 0)),
            }
            job.summary = summary
            job.preview = {
                "overlay_url": f"/download/{job.id}/preview_png",
                "bounds": [[sw[1], sw[0]], [ne[1], ne[0]]],
                "turbines_geojson": {"type": "FeatureCollection", "features": turb_features},
                "points_geojson": {"type": "FeatureCollection", "features": point_features},
            }

            job.outputs = {
                "asc": f"/download/{job.id}/asc",
                 "geotiff": f"/download/{job.id}/geotiff",
                 "report_pdf": f"/download/{job.id}/report_pdf",
                "preview_png": f"/download/{job.id}/preview_png",
            }

            pdf = _generate_pdf(job, str(png_path), lang)
            _upsert_file(db, job_id, "report_pdf", pdf)
            job.status = "completed"
            job.progress_pct = 100
            job.progress_message = tr(lang, "progress.done")
            job.updated_at = datetime.now(UTC)
            db.commit()
        except Exception as exc:  # noqa
            job.status = "failed"
            job.error_code = "PROCESSING_ERROR"
            job.error_detail = str(exc)

            job.outputs = {
                "asc": f"/download/{job.id}/asc",
                "geotiff": f"/download/{job.id}/geotiff",
                "preview_png": f"/download/{job.id}/preview_png",
                 "report_pdf": f"/download/{job.id}/report_pdf"
            }

            db.commit()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/jobs")
def create_job(payload: JobCreate, background_tasks: BackgroundTasks, accept_language: str | None = Header(default=None)):
    lang = detect_lang(accept_language, payload.lang)
    if not 0 <= payload.simulation.min_solar_elevation_deg <= 20:
        raise HTTPException(400, detail=tr(lang, "errors.min_solar"))

    job_id = secrets.token_hex(12)
    now = datetime.now(UTC)
    with Session(engine) as db:
        job = Job(
            id=job_id,
            lang=lang,
            payload=payload.model_dump(),
            status="queued",
            progress_pct=0,
            progress_message=tr(lang, "progress.queued"),
            expires_at=now + timedelta(hours=JOB_EXPIRY_HOURS),
            user_email=payload.user_email,
        )
        db.add(job)
        db.commit()
    background_tasks.add_task(_process_job, job_id)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with Session(engine) as db:
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        outputs = {}
        if job.paid:
            for f in db.execute(select(JobFile).where(JobFile.job_id == job_id)).scalars().all():
                outputs[f.kind] = f"/download/{job_id}/{f.kind}"
        return {
            "status": job.status,
            "progress_pct": job.progress_pct,
            "progress_message": job.progress_message,
            "summary": job.summary,
            "price_quote": job.price_quote,
            "preview": job.preview,
            "outputs": outputs,
            "paid": job.paid,
            "expires_at": job.expires_at,
            "error": {"code": job.error_code, "detail": job.error_detail} if job.error_code else None,
        }


@app.post("/api/jobs/{job_id}/checkout")
def checkout(job_id: str, req: CheckoutRequest):
    with Session(engine) as db:
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        if not job.price_quote:
            raise HTTPException(400, "price not ready")
        amount = int(round(float(job.price_quote["total"]) * 100))
        if STRIPE_SECRET_KEY:
            session = stripe.checkout.Session.create(
                line_items=[{"price_data": {"currency": "eur", "unit_amount": amount, "product_data": {"name": "Wind Shadow Studio"}}, "quantity": 1}],
                mode="payment",
                success_url=req.success_url or f"{PUBLIC_BASE_URL}/success?job_id={job_id}",
                cancel_url=req.cancel_url or f"{PUBLIC_BASE_URL}/cancel?job_id={job_id}",
                metadata={"job_id": job_id},
            )
            job.checkout_session_id = session.id
            db.commit()
            return {"checkout_url": session.url}
        token = f"mock_{job_id}"
        job.checkout_session_id = token
        db.commit()
        return {"checkout_url": f"{PUBLIC_BASE_URL}/mock-checkout/{job_id}"}


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None)):
    payload = await request.body()
    if STRIPE_WEBHOOK_SECRET and stripe_signature:
        try:
            event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
        except SignatureVerificationError as exc:
            raise HTTPException(400, str(exc)) from exc
    else:
        event = json.loads(payload.decode("utf-8"))

    if event.get("type") == "checkout.session.completed":
        obj = event.get("data", {}).get("object", {})
        job_id = obj.get("metadata", {}).get("job_id") or obj.get("job_id")
        if not job_id:
            return {"ok": True}
        with Session(engine) as db:
            job = db.get(Job, job_id)
            if not job:
                return {"ok": True}
            job.paid = True
            _save_calendar(job, db)
            db.commit()
    return {"ok": True}


@app.get("/download/{job_id}/{kind}")
def download(job_id: str, kind: str):
    allowed = {"asc", "geotiff", "report_pdf", "calendar_csv", "calendar_json", "preview_png"}
    if kind not in allowed:
        raise HTTPException(404, "not found")
    with Session(engine) as db:
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        now = datetime.now(UTC)
        if job.expires_at < now:
            raise HTTPException(410, "expired")
        if kind != "preview_png" and not job.paid:
            raise HTTPException(403, "payment required")
        f = db.execute(select(JobFile).where(JobFile.job_id == job_id, JobFile.kind == kind)).scalar_one_or_none()
        if not f:
            raise HTTPException(404, "file not found")
        media = "application/octet-stream"
        if kind == "report_pdf":
            media = "application/pdf"
        elif kind == "preview_png":
            media = "image/png"
        return FileResponse(f.path, media_type=media, filename=Path(f.path).name)
