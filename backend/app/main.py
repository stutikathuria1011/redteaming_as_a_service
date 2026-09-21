from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router


app = FastAPI(
    title="Red Teaming as a Service",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "message": "Red Teaming as a Service API",
        "status": "running",
    }


app.include_router(health_router)
app.include_router(jobs_router)