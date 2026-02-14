from fastapi import FastAPI

app = FastAPI()


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.post('/jobs')
def create_job() -> dict[str, str]:
    return {'status': 'ok'}
