import base64
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import httpx

from app.agents import push_file_to_branch
from app.core.config import settings

logger = logging.getLogger("FilesRouter")

router = APIRouter()


@router.post("/api/fetch-file")
async def fetch_file_content(payload: dict):
    """Fetch file content from GitHub"""
    owner = payload.get("owner")
    repo = payload.get("repo")
    path = payload.get("path")
    ref = payload.get("ref", "main")
    github_token = payload.get("github_token")

    if not all([owner, repo, path, github_token]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3.raw"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get(url, headers=headers, params={"ref": ref})
            if r.status_code == 200:
                return {"ok": True, "content": r.text}
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


@router.get("/api/proxy")
async def proxy_content(url: str, github_token: Optional[str] = None):
    """Proxy content from external URL"""
    if not url:
        raise HTTPException(status_code=400, detail="Missing URL")
        
    headers = {}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
        
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail="Failed to fetch content")
            return JSONResponse({"content": r.text})
        except httpx.RequestError as e:
            logger.error(f"Proxy error: {e}")
            raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")


@router.post("/api/commit-file")
async def commit_file(payload: dict):
    """Commit file to GitHub"""
    owner = payload.get("owner")
    repo = payload.get("repo")
    path = payload.get("path")
    content = payload.get("content")
    message = payload.get("message", "Update file via Dashboard")
    sha = payload.get("sha")
    branch = payload.get("branch")
    github_token = payload.get("github_token")
    
    if not all([owner, repo, path, content, sha, github_token]):
        raise HTTPException(status_code=400, detail="Missing required fields")
        
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    
    content_bytes = content.encode('utf-8')
    base64_content = base64.b64encode(content_bytes).decode('utf-8')
    
    data = {
        "message": message,
        "content": base64_content,
        "sha": sha
    }
    if branch:
        data["branch"] = branch
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.put(url, headers=headers, json=data)
            if r.status_code in [200, 201]:
                return {
                    "ok": True, 
                    "msg": "File saved successfully", 
                    "new_sha": r.json()["content"]["sha"]
                }
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


@router.post("/api/push-to-branch")
async def push_to_branch(payload: dict):
    """Push file to branch"""
    owner = payload.get("owner")
    repo = payload.get("repo")
    path = payload.get("path")
    content = payload.get("content")
    message = payload.get("message", "Update file via AI Editor")
    sha = payload.get("sha")
    branch = payload.get("branch")
    github_token = payload.get("github_token")
    
    if not all([owner, repo, path, content, sha, branch, github_token]):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    result = await push_file_to_branch(
        owner, repo, path, content, message, sha, branch, github_token
    )
    
    return result


@router.post("/api/save-branch")
async def save_branch(payload: dict):
    """Create a new branch"""
    owner = payload.get("owner")
    repo = payload.get("repo")
    base_branch = payload.get("base_branch", "main")
    new_branch_name = payload.get("new_branch_name")
    github_token = payload.get("github_token")
    
    if not all([owner, repo, new_branch_name, github_token]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get SHA of base branch
        ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{base_branch}"
        try:
            ref_res = await client.get(ref_url, headers=headers)
            ref_res.raise_for_status()
            sha = ref_res.json()["object"]["sha"]
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code, 
                detail=f"Base branch not found: {e.response.text}"
            )

        # Create new branch
        create_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
        try:
            create_res = await client.post(create_url, headers=headers, json={
                "ref": f"refs/heads/{new_branch_name}",
                "sha": sha
            })
            
            if create_res.status_code == 201:
                return {"ok": True, "msg": f"Branch {new_branch_name} created successfully"}
            else:
                return JSONResponse(
                    {"ok": False, "error": create_res.text},
                    status_code=create_res.status_code
                )
        except Exception as e:
            return JSONResponse(
                {"ok": False, "error": str(e)},
                status_code=500
            )
