from fastapi import FastAPI

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


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }