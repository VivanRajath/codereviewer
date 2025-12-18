import os
import json
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.exceptions import (
    GitHubAPIError,
    AuthenticationError,
    WebhookValidationError,
    MissingConfigurationError
)

# Import routers
from app.api.routers import auth, webhooks, analysis, repos, files

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("MainAPI")

# Create FastAPI app
app = FastAPI(
    title="Lyzer AI - Code Review Agent",
    description="Automated PR review system with multi-agent AI analysis",
    version="2.0.0"
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware, 
    secret_key=settings.SECRET_KEY
)


# Global exception handlers
@app.exception_handler(GitHubAPIError)
async def github_api_exception_handler(request: Request, exc: GitHubAPIError):
    """Handle GitHub API errors"""
    logger.error(f"GitHub API Error: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "type": "github_api_error"}
    )


@app.exception_handler(AuthenticationError)
async def auth_exception_handler(request: Request, exc: AuthenticationError):
    """Handle authentication errors"""
    logger.error(f"Authentication Error: {exc.detail}")
    return JSONResponse(
        status_code=401,
        content={"error": exc.detail, "type": "authentication_error"}
    )


@app.exception_handler(WebhookValidationError)
async def webhook_exception_handler(request: Request, exc: WebhookValidationError):
    """Handle webhook validation errors"""
    logger.error(f"Webhook Validation Error: {exc.detail}")
    return JSONResponse(
        status_code=401,
        content={"error": exc.detail, "type": "webhook_validation_error"}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions"""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "type": "server_error"}
    )


# Register routers
app.include_router(auth.router, tags=["Authentication"])
app.include_router(webhooks.router, tags=["Webhooks"])
app.include_router(analysis.router, tags=["Analysis"])
app.include_router(repos.router, tags=["Repositories"])
app.include_router(files.router, tags=["Files"])


# Data persistence (TODO: Replace with database)
DATA_DIR = Path("data")
DATA_FILE = DATA_DIR / "analysis_results.json"

def load_data():
    """Load analysis results from JSON file"""
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text())
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return []

def save_data(data):
    """Save analysis results to JSON file"""
    try:
        DATA_DIR.mkdir(exist_ok=True)
        DATA_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        logger.error(f"Error saving data: {e}")

# Global state (TODO: Replace with database)
analysis_results = load_data()


# Static routes
@app.get("/")
async def home():
    """Serve login page"""
    return FileResponse("static/index.html")


@app.get("/api/activity-logs")
async def get_activity_logs(request: Request):
    """Get activity logs (commits, file changes, analyses)"""
    # TODO: Implement proper activity tracking
    # For now, return analysis results
    return {
        "commits": [],
        "fileChanges": [],
        "analyses": analysis_results[:10]
    }


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# Startup event
@app.on_event("startup")
async def startup_event():
    """Log startup information"""
    logger.info("Starting AI Code Review Agent")
    logger.info(f"GitHub OAuth configured: {settings.validate_oauth()}")
    logger.info(f"Webhook secret configured: {settings.validate_webhook_secret()}")
    logger.info(f"Grok keys available: {len(settings.GROK_KEYS)}")
    logger.info(f"Gemini keys available: {len(settings.GEMINI_KEYS)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
