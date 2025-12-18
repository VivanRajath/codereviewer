import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse
import httpx

from app.agents import run_multi_agent_review, push_file_to_branch
from app.api.routers.webhooks import fetch_pr_files
from app.core.config import settings
from app.core.exceptions import GitHubAPIError

logger = logging.getLogger("ReposRouter")

router = APIRouter()


@router.get("/api/repos")
async def get_repositories(github_token: Optional[str] = Header(None)):
    """Fetch user repositories"""
    if not github_token:
        raise HTTPException(status_code=401, detail="Missing GitHub Token")

    url = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get(url, headers=headers, params={"sort": "updated", "per_page": 100})
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            raise GitHubAPIError(e.response.text, e.response.status_code)


@router.get("/api/repos/{owner}/{repo}/prs")
async def get_repo_prs(owner: str, repo: str, github_token: Optional[str] = Header(None)):
    """Fetch pull requests for a repository"""
    if not github_token:
        raise HTTPException(status_code=401, detail="Missing GitHub Token")

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get(
                url, 
                headers=headers, 
                params={"state": "all", "sort": "updated", "direction": "desc", "per_page": 100}
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            raise GitHubAPIError(e.response.text, e.response.status_code)


@router.get("/api/repos/{owner}/{repo}/prs/{pr_number}")
async def get_pr_details(
    owner: str, 
    repo: str, 
    pr_number: int, 
    github_token: Optional[str] = Header(None)
):
    """Fetch PR details and run analysis"""
    if not github_token:
        raise HTTPException(status_code=401, detail="Missing GitHub Token")

    # Fetch PR metadata
    pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            pr_res = await client.get(pr_url, headers=headers)
            pr_res.raise_for_status()
            pr_data = pr_res.json()
        except httpx.HTTPStatusError as e:
            raise GitHubAPIError(e.response.text, e.response.status_code)

    files = await fetch_pr_files(owner, repo, pr_number, github_token)
    analysis = run_multi_agent_review(files)
    
    # Store analysis
    from app.main import analysis_results, save_data
    
    analysis_results.insert(0, {
        "ok": True,
        "action": "analyzed",
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "changed_files_count": len(files),
        "analysis": analysis,
        "timestamp": ""
    })
    
    if len(analysis_results) > 50:
        analysis_results.pop()
    
    save_data(analysis_results)

    return {
        "pr": pr_data,
        "files": files,
        "analysis": analysis
    }


@router.post("/api/repos/{owner}/{repo}/prs/{pr_number}/analyze")
async def analyze_pr_endpoint(owner: str, repo: str, pr_number: int, payload: dict):
    """Run analysis on PR"""
    github_token = payload.get("github_token")
    
    if not github_token:
        raise HTTPException(status_code=401, detail="Missing GitHub Token")
    
    try:
        files = await fetch_pr_files(owner, repo, pr_number, github_token)
        
        if not files:
            return JSONResponse({
                "ok": False,
                "error": "No files found in PR"
            }, status_code=404)
        
        analysis = run_multi_agent_review(files)
        
        # Store analysis
        from app.main import analysis_results, save_data
        
        analysis_results.insert(0, {
            "ok": True,
            "action": "analyzed",
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "changed_files_count": len(files),
            "analysis": analysis,
            "timestamp": ""
        })
        
        if len(analysis_results) > 50:
            analysis_results.pop()
        
        save_data(analysis_results)
        
        return JSONResponse({
            "ok": True,
            "analysis": analysis
        })
        
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}")
        return JSONResponse({
            "ok": False,
            "error": str(e)
        }, status_code=500)


@router.post("/api/merge-pr")
async def merge_pr(payload: dict):
    """Merge a pull request"""
    owner = payload.get("owner")
    repo = payload.get("repo")
    pr_number = payload.get("pr_number")
    github_token = payload.get("github_token")
    
    token = github_token or settings.GITHUB_TOKEN
    if not token:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN not configured")
        
    if not all([owner, repo, pr_number]):
        raise HTTPException(status_code=400, detail="Missing owner, repo, or pr_number")
        
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.put(url, headers=headers, json={"merge_method": "merge"})
            if r.status_code == 200:
                return JSONResponse({"ok": True, "msg": "PR merged successfully"})
            elif r.status_code == 405:
                return JSONResponse(
                    {"ok": False, "error": "PR is not mergeable. It may have conflicts or be a draft."},
                    status_code=405
                )
            else:
                return JSONResponse(
                    {"ok": False, "error": r.text},
                    status_code=r.status_code
                )
        except Exception as e:
            return JSONResponse(
                {"ok": False, "error": str(e)},
                status_code=500
            )
