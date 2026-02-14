from fastapi import FastAPI

app = FastAPI(title="WTG Shadow Service")

@app.get("/health")
def health():
    return {"status": "ok"}
