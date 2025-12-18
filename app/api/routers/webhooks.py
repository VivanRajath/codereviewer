import os
import hmac
import hashlib
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx

from app.core.config import settings
from app.core.exceptions import WebhookValidationError, GitHubAPIError
from app.agents import run_multi_agent_review

logger = logging.getLogger("WebhookRouter")

router = APIRouter()


def verify_signature(body_bytes: bytes, signature_header: Optional[str]) -> bool:
    """Verify GitHub webhook signature"""
    if not settings.GITHUB_WEBHOOK_SECRET:
        # In production, fail if secret is not configured
        logger.warning("Webhook secret not configured - this is insecure in production!")
        return True
    
    if signature_header is None:
        return False

    try:
        sha_name, signature = signature_header.split("=")
    except ValueError:
        return False

    if sha_name != "sha256":
        return False

    mac = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(), 
        msg=body_bytes, 
        digestmod=hashlib.sha256
    )
    computed = mac.hexdigest()

    return hmac.compare_digest(computed, signature)


async def fetch_pr_files(
    owner: str, 
    repo: str, 
    pr_number: int, 
    github_token: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Fetch changed files for a pull request"""
    token = github_token or settings.GITHUB_TOKEN
    if not token:
        raise GitHubAPIError("GITHUB_TOKEN not configured")
        
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    files = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        page = 1
        while True:
            try:
                r = await client.get(url, headers=headers, params={"per_page": 100, "page": page})
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise GitHubAPIError(f"Failed to fetch PR files: {e.response.text}", e.response.status_code)
            
            data = r.json()

            if not data:
                break

            for f in data:
                files.append({
                    "filename": f.get("filename"),
                    "status": f.get("status"),
                    "patch": f.get("patch"),
                    "raw_url": f.get("raw_url"),
                    "sha": f.get("sha")
                })

            if len(data) < 100:
                break

            page += 1

    return files


@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None)
):
    """Handle GitHub webhook events"""
    body_bytes = await request.body()

    if not verify_signature(body_bytes, x_hub_signature_256):
        raise WebhookValidationError()

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if x_github_event != "pull_request":
        return JSONResponse({"ok": True, "msg": f"Ignored event: {x_github_event}"})

    action = payload.get("action")
    allowed_actions = {"opened", "synchronize", "reopened"}

    if action not in allowed_actions:
        return JSONResponse({"ok": True, "msg": f"No-op action: {action}"})

    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    owner = repo.get("owner", {}).get("login")
    repo_name = repo.get("name")
    pr_number = pr.get("number")

    if not all([owner, repo_name, pr_number]):
        raise HTTPException(status_code=400, detail="Missing repo/pr info")

    try:
        files_raw = await fetch_pr_files(owner, repo_name, pr_number)
    except GitHubAPIError as e:
        return JSONResponse(
            {"ok": False, "error": str(e.detail)},
            status_code=e.status_code
        )

    analysis_report = run_multi_agent_review(files_raw)

    result_data = {
        "ok": True,
        "action": action,
        "owner": owner,
        "repo": repo_name,
        "pr_number": pr_number,
        "changed_files_count": len(files_raw),
        "analysis": analysis_report,
        "timestamp": ""
    }
    
    # Import here to avoid circular dependency
    from app.main import analysis_results, save_data
    
    analysis_results.insert(0, result_data)
    if len(analysis_results) > 50:
        analysis_results.pop()
    
    save_data(analysis_results)

    return JSONResponse(result_data)
