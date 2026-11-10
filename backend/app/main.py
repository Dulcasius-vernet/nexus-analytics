import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth import router as auth_router
from app.api.workspaces import router as workspaces_router
from app.api.routes import router as api_router
from app.api.models import HealthResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = FastAPI(title="Nexus Analytics API", version="0.2.0", description="AI-augmented business intelligence and predictive analytics")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)

@app.get("/api/v1/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", service="nexus-analytics-api")

app.include_router(auth_router, prefix="/api/v1")
app.include_router(workspaces_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/v1")
