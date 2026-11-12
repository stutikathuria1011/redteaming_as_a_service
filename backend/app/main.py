from dotenv import load_dotenv

# Load backend/.env before anything reads the environment (GROQ_API_KEY etc.).
load_dotenv()

from fastapi import FastAPI  # noqa: E402

from app.api.routes.health import router as health_router  # noqa: E402
from app.api.routes.jobs import router as jobs_router  # noqa: E402


app = FastAPI(
    title="Red Teaming as a Service",
    version="0.2.0",
)


@app.get("/")
def root():
    return {
        "message": "Red Teaming as a Service API",
        "status": "running",
    }


app.include_router(health_router)
app.include_router(jobs_router)