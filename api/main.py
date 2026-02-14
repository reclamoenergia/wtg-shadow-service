from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI(title="WTG Shadow Service")

OUTPUTS_DIR = Path("outputs")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/simulate")
def simulate():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"simulation_{uuid4().hex}.asc"
    output_path = OUTPUTS_DIR / filename

    # Placeholder output file for demo API behaviour.
    output_path.write_text("ncols 1\nnrows 1\nxllcorner 0\nyllcorner 0\ncellsize 1\nNODATA_value -9999\n0\n")

    return {
        "status": "completed",
        "filename": filename,
        "download_url": f"/results/{filename}",
    }


@app.get("/results/{filename}")
def get_result(filename: str):
    # No traversal and only .asc files are allowed.
    if filename != Path(filename).name or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if Path(filename).suffix.lower() != ".asc":
        raise HTTPException(status_code=400, detail="Only .asc files are allowed")

    file_path = OUTPUTS_DIR / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=file_path, media_type="text/plain", filename=filename)
