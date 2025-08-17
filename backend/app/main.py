from fastapi import FastAPI
from app.routers.process import router as process_router

app = FastAPI(title="Intern Demo Backend (No-AI)")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

# ここが prefix="/process" なので、最終URLは /process
app.include_router(process_router, prefix="/process", tags=["process"])
