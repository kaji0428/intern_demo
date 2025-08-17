from fastapi import FastAPI
from app.routers.process import router as process_router

app = FastAPI(title="Intern Demo Backend")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

app.include_router(process_router, prefix="/process", tags=["process"])
