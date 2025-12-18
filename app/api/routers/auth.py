import os
from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import RedirectResponse, FileResponse
from authlib.integrations.starlette_client import OAuth
from app.core.config import settings
from app.core.exceptions import AuthenticationError
import logging

logger = logging.getLogger("AuthRouter")

router = APIRouter()

# OAuth Setup
if not settings.validate_oauth():
    raise RuntimeError("GitHub OAuth credentials missing. Check .env file.")

oauth = OAuth()
oauth.register(
    name='github',
    client_id=settings.GITHUB_CLIENT_ID,
    client_secret=settings.GITHUB_CLIENT_SECRET,
    access_token_url='https://github.com/login/oauth/access_token',
    authorize_url='https://github.com/login/oauth/authorize',
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email repo'}
)


@router.get("/login/oauth")
async def github_login(request: Request):
    """Initiate GitHub OAuth login"""
    base_url = settings.BASE_URL
    if base_url:
        base_url = base_url.rstrip("/")
        redirect_uri = f"{base_url}/login/callback"
    else:
        redirect_uri = request.url_for("github_callback")
        
        if "onrender.com" in str(redirect_uri) and str(redirect_uri).startswith("http://"):
            redirect_uri = str(redirect_uri).replace("http://", "https://")
    
    if request.url.hostname == "127.0.0.1":
        redirect_uri = "http://localhost:8000/login/callback"
        
    if "localhost" in str(redirect_uri) or "127.0.0.1" in str(redirect_uri):
        redirect_uri = "http://localhost:8000/login/callback"
        
    logger.info(f"Redirecting to GitHub with redirect_uri={redirect_uri}")
    return await oauth.github.authorize_redirect(request, redirect_uri)


@router.get("/login/callback")
async def github_callback(request: Request):
    """Handle GitHub OAuth callback"""
    try:
        token = await oauth.github.authorize_access_token(request)
    except Exception as e:
        logger.error(f"OAuth error: {e}")
        raise AuthenticationError("OAuth failed")

    access_token = token.get("access_token")
    if not access_token:
        raise AuthenticationError("No access token returned")

    return RedirectResponse(
        url=f"/dashboard#token={access_token}",
        status_code=302
    )


@router.get("/dashboard")
async def dashboard():
    """Serve dashboard page"""
    return FileResponse("static/dashboard.html")


@router.get("/logout")
async def logout(request: Request):
    """Logout user"""
    request.session.clear()
    return RedirectResponse(url="/")
