import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.agents import (
    run_multi_agent_review,
    chat_with_agent,
    analyze_full_code,
    auto_fix_and_push,
    generate_fix_for_issue
)
from app.api.routers.webhooks import fetch_pr_files
from app.core.config import settings
from app.core.exceptions import GitHubAPIError

logger = logging.getLogger("AnalysisRouter")

router = APIRouter()


@router.post("/analyze-pr")
async def analyze_pr_manual(payload: dict):
    """Manually trigger PR analysis"""
    owner = payload.get("owner")
    repo = payload.get("repo")
    pr_number = payload.get("pr_number")
    github_token = payload.get("github_token")
    
    if not all([owner, repo, pr_number]):
        raise HTTPException(status_code=400, detail="Missing owner, repo, or pr_number")
        
    try:
        files_raw = await fetch_pr_files(owner, repo, pr_number, github_token)
    except GitHubAPIError as e:
        return JSONResponse(
            {"ok": False, "error": str(e.detail)},
            status_code=e.status_code
        )
        
    analysis_report = run_multi_agent_review(files_raw)
    
    return JSONResponse({
        "ok": True,
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "analysis": analysis_report
    })


@router.post("/api/analyze-code")
async def analyze_code_endpoint(payload: dict):
    """Analyze code using AI"""
    code = payload.get("code")
    filename = payload.get("filename", "unknown.py")
    
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")
        
    analysis = analyze_full_code(code, filename)
    return {"ok": True, "analysis": analysis}


@router.post("/api/auto-fix")
async def auto_fix_endpoint(payload: dict):
    """Auto-fix code issues and push"""
    owner = payload.get("owner")
    repo = payload.get("repo")
    branch = payload.get("branch")
    filename = payload.get("filename")
    code = payload.get("code")
    issues = payload.get("issues", [])
    github_token = payload.get("github_token")

    if not all([owner, repo, branch, filename, code, github_token]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    result = auto_fix_and_push(owner, repo, branch, filename, code, issues, github_token)
    return result


@router.post("/api/generate-fix")
async def generate_fix_endpoint(payload: dict):
    """Generate fix for a specific issue"""
    code = payload.get("code")
    issue = payload.get("issue")
    
    if not code or not issue:
        raise HTTPException(status_code=400, detail="Missing code or issue")
        
    result = generate_fix_for_issue(code, issue)
    return result


@router.post("/api/chat")
async def chat_endpoint(payload: dict):
    """Chat with AI assistant about code"""
    message = payload.get("message")
    context = payload.get("context", {})
    history = payload.get("history", [])
    
    if not message:
        raise HTTPException(status_code=400, detail="Message required")

    result = chat_with_agent(message, context, history)
    return result
