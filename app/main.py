# app/main.py
import os
import hmac
import hashlib
import logging
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import httpx
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth


load_dotenv(override=True)
print("DEBUG: Loading .env file")
print(f"DEBUG: GITHUB_CLIENT_ID={os.getenv('GITHUB_CLIENT_ID')}")
print(f"DEBUG: Current Working Directory: {os.getcwd()}")


# Setup logger
logger = logging.getLogger("MainAPI")
logger.setLevel(logging.DEBUG)

from app.agents import run_multi_agent_review, chat_with_agent

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

# We don't strictly enforce these for the manual endpoint, but needed for webhook
# if not GITHUB_TOKEN:
#     raise RuntimeError("GITHUB_TOKEN not set in environment")

app = FastAPI(title="PR Webhook Receiver")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "secret"))

# OAuth Setup

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
    raise RuntimeError("GitHub OAuth credentials missing. Check .env file.")

oauth = OAuth()
oauth.register(
    name='github',
    client_id=GITHUB_CLIENT_ID,
    client_secret=GITHUB_CLIENT_SECRET,
    access_token_url='https://github.com/login/oauth/access_token',
    authorize_url='https://github.com/login/oauth/authorize',
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email repo'}
)

# -------------------------------
# Verify webhook signature
# -------------------------------
def verify_signature(body_bytes: bytes, signature_header: Optional[str]) -> bool:
    if not WEBHOOK_SECRET:
        return True # Dev mode bypass if secret not set
    if signature_header is None:
        return False

    try:
        sha_name, signature = signature_header.split("=")
    except ValueError:
        return False

    if sha_name != "sha256":
        return False

    mac = hmac.new(WEBHOOK_SECRET.encode(), msg=body_bytes, digestmod=hashlib.sha256)
    computed = mac.hexdigest()

    return hmac.compare_digest(computed, signature)


# -------------------------------
# Convert unified diff patch → hunks
# -------------------------------
def parse_patch_to_hunks(patch: str):
    if not patch:
        return []

    hunks = []
    lines = patch.split("\n")
    current_hunk = []

    for line in lines:
        if line.startswith("@@"):
            if current_hunk:
                hunks.append("\n".join(current_hunk))
            current_hunk = [line]
        else:
            current_hunk.append(line)

    if current_hunk:
        hunks.append("\n".join(current_hunk))

    return hunks


# -------------------------------
# Fetch list of PR changed files
# -------------------------------
async def fetch_pr_files(owner: str, repo: str, pr_number: int, github_token: Optional[str] = None):
    token = github_token or GITHUB_TOKEN
    if not token:
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN not configured")
        
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    files = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        page = 1
        while True:
            r = await client.get(url, headers=headers, params={"per_page": 100, "page": page})
            r.raise_for_status()
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


# -------------------------------
# Webhook Handler
# -------------------------------
@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None)
):

    body_bytes = await request.body()

    # Verify webhook signature
    if not verify_signature(body_bytes, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Only process pull_request events
    if x_github_event != "pull_request":
        return JSONResponse({"ok": True, "msg": f"ignored event: {x_github_event}"})

    action = payload.get("action")
    allowed_actions = {"opened", "synchronize", "reopened"}

    if action not in allowed_actions:
        return JSONResponse({"ok": True, "msg": f"no-op action: {action}"})

    # Extract basic info
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    owner = repo.get("owner", {}).get("login")
    repo_name = repo.get("name")
    pr_number = pr.get("number")

    if not all([owner, repo_name, pr_number]):
        raise HTTPException(status_code=400, detail="Missing repo/pr info")

    # Fetch changed files
    try:
        files_raw = await fetch_pr_files(owner, repo_name, pr_number)
    except httpx.HTTPStatusError as e:
        return JSONResponse(
            {"ok": False, "error": str(e), "status_code": e.response.status_code},
            status_code=500
        )

    # -------------------------------
    # Run AI analysis
    # -------------------------------
    # We pass the raw files (with patches) to the agent
    analysis_report = run_multi_agent_review(files_raw)

    # -------------------------------
    # Final API response
    # -------------------------------
    result_data = {
        "ok": True,
        "action": action,
        "owner": owner,
        "repo": repo_name,
        "pr_number": pr_number,
        "changed_files_count": len(files_raw),
        "analysis": analysis_report,
        "timestamp": os.getenv("TIMESTAMP", "") # You might want to add a real timestamp here
    }
    
    # Store in memory (limit to last 50)
    analysis_results.insert(0, result_data)
    if len(analysis_results) > 50:
        analysis_results.pop()
    
    save_data(analysis_results)

    return JSONResponse(result_data)

# -------------------------------
# OAuth Routes
# -------------------------------

# Login route
@app.get("/login/oauth")
async def github_login(request: Request):
    # Fix CSRF/State mismatch by ensuring we are on localhost if that is the redirect target
    if request.url.hostname == "127.0.0.1":
        return RedirectResponse(str(request.url).replace("127.0.0.1", "localhost"))

    # Determine scheme (http vs https)
    # Using 'http' for localhost explicitly to avoid proxy issues, or matching the request
    redirect_uri = request.url_for("github_callback")
    
    # For localhost development, force http://localhost if the request came that way
    # This helps if for some reason it resolves to 127.0.0.1 but GitHub expects localhost
    if "localhost" in str(redirect_uri) or "127.0.0.1" in str(redirect_uri):
        redirect_uri = "http://localhost:8000/login/callback"
        
    print(f"DEBUG: Redirecting to GitHub with redirect_uri={redirect_uri}")
    return await oauth.github.authorize_redirect(request, redirect_uri)


# Callback route
@app.get("/login/callback")
async def github_callback(request: Request):
    try:
        token = await oauth.github.authorize_access_token(request)
    except Exception as e:
        logger.error(f"OAuth error: {e}")
        raise HTTPException(status_code=400, detail="OAuth failed")

    access_token = token.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token returned")

    # Redirect to dashboard with token
    return RedirectResponse(
        url=f"/dashboard#token={access_token}",
        status_code=302
    )

@app.get("/dashboard")
async def dashboard(request: Request):
    return FileResponse("static/dashboard.html")

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

# -------------------------------
# Manual Trigger Endpoint
# -------------------------------
@app.post("/analyze-pr")
async def analyze_pr_manual(payload: dict):
    owner = payload.get("owner")
    repo = payload.get("repo")
    pr_number = payload.get("pr_number")
    github_token = payload.get("github_token")
    
    if not all([owner, repo, pr_number]):
        raise HTTPException(status_code=400, detail="Missing owner, repo, or pr_number")
        
    # Fetch changed files
    try:
        files_raw = await fetch_pr_files(owner, repo, pr_number, github_token)
    except httpx.HTTPStatusError as e:
        return JSONResponse(
            {"ok": False, "error": str(e), "status_code": e.response.status_code},
            status_code=500
        )
        
    analysis_report = run_multi_agent_review(files_raw)
    
    return JSONResponse({
        "ok": True,
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "analysis": analysis_report
    })

# -------------------------------
# Merge PR Endpoint
# -------------------------------
@app.post("/api/merge-pr")
async def merge_pr(payload: dict):
    owner = payload.get("owner")
    repo = payload.get("repo")
    pr_number = payload.get("pr_number")
    github_token = payload.get("github_token")
    
    token = github_token or GITHUB_TOKEN
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
                return JSONResponse({"ok": True, "msg": "PR Merged Successfully!"})
            elif r.status_code == 405:
                return JSONResponse(
                    {"ok": False, "error": "PR is not mergeable. It may have conflicts or be a draft."},
                    status_code=405
                )
            else:
                return JSONResponse(
                    {"ok": False, "error": r.text, "status_code": r.status_code},
                    status_code=r.status_code
                )
        except Exception as e:
             return JSONResponse(
                {"ok": False, "error": str(e)},
                status_code=500
            )

# -------------------------------
# NEW: Fetch User Repositories
# -------------------------------
@app.get("/api/repos")
async def get_repositories(github_token: Optional[str] = Header(None)):
    if not github_token:
        raise HTTPException(status_code=401, detail="Missing GitHub Token")

    url = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=headers, params={"sort": "updated", "per_page": 100})
        if r.status_code != 200:
             raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()

# -------------------------------
# NEW: Fetch PRs for a Repo
# -------------------------------
@app.get("/api/repos/{owner}/{repo}/prs")
async def get_repo_prs(owner: str, repo: str, github_token: Optional[str] = Header(None)):
    if not github_token:
        raise HTTPException(status_code=401, detail="Missing GitHub Token")

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=headers, params={"state": "all", "sort": "updated", "direction": "desc", "per_page": 100})
        if r.status_code != 200:
             raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()

# -------------------------------
# NEW: Fetch PR Files
# -------------------------------
async def fetch_pr_files(owner: str, repo: str, pr_number: int, github_token: str) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.get(url, headers=headers)
        if res.status_code != 200:
            # Log error or return empty list, but better to raise to know why
            print(f"Error fetching files: {res.text}")
            return []
        return res.json()

# -------------------------------
# NEW: Fetch PR Details (Files + Analysis)
# -------------------------------
@app.get("/api/repos/{owner}/{repo}/prs/{pr_number}")
async def get_pr_details(owner: str, repo: str, pr_number: int, github_token: Optional[str] = Header(None)):
    if not github_token:
        raise HTTPException(status_code=401, detail="Missing GitHub Token")

    # 1. Fetch PR metadata
    pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        pr_res = await client.get(pr_url, headers=headers)
        if pr_res.status_code != 200:
            raise HTTPException(status_code=pr_res.status_code, detail=pr_res.text)
        pr_data = pr_res.json()

    # 2. Fetch Files
    files = await fetch_pr_files(owner, repo, pr_number, github_token)

    # 3. Run Analysis - Always run fresh analysis on each PR view
    analysis = run_multi_agent_review(files)
    
    # Save to history
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
    
    # Keep only last 50 results
    if len(analysis_results) > 50:
        analysis_results.pop()
    
    save_data(analysis_results)

    return {
        "pr": pr_data,
        "files": files,
        "analysis": analysis
    }

# -------------------------------
# NEW: Run Analysis on PR (for Report Tab)
# -------------------------------
@app.post("/api/repos/{owner}/{repo}/prs/{pr_number}/analyze")
async def analyze_pr_endpoint(owner: str, repo: str, pr_number: int, payload: dict):
    github_token = payload.get("github_token")
    
    if not github_token:
        raise HTTPException(status_code=401, detail="Missing GitHub Token")
    
    try:
        # 1. Fetch PR files
        files = await fetch_pr_files(owner, repo, pr_number, github_token)
        
        if not files:
            return JSONResponse({
                "ok": False,
                "error": "No files found in PR"
            }, status_code=404)
        
        # 2. Run multi-agent analysis
        analysis = run_multi_agent_review(files)
        
        # 3. Save to history
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
        
        # Keep only last 50 results
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

# -------------------------------
# NEW: Chat with Agent
# -------------------------------
@app.post("/api/chat")
async def chat_endpoint(payload: dict):
    message = payload.get("message")
    context = payload.get("context") # Previous analysis or code snippets
    history = payload.get("history", [])
    
    if not message:
        raise HTTPException(status_code=400, detail="Message required")

    response = chat_with_agent(message, context, history)
    return {"response": response}

# -------------------------------
# NEW: Save as Branch
# -------------------------------
@app.post("/api/save-branch")
async def save_branch(payload: dict):
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
        # 1. Get SHA of base branch
        ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{base_branch}"
        ref_res = await client.get(ref_url, headers=headers)
        if ref_res.status_code != 200:
             raise HTTPException(status_code=ref_res.status_code, detail=f"Base branch not found: {ref_res.text}")
        
        sha = ref_res.json()["object"]["sha"]

        # 2. Create new branch
        create_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
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

# -------------------------------
# NEW: Fetch Single File Content
# -------------------------------
@app.post("/api/fetch-file")
async def fetch_file_content(payload: dict):
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
        "Accept": "application/vnd.github.v3.raw" # Request raw content
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=headers, params={"ref": ref})
        if r.status_code == 200:
            return {"ok": True, "content": r.text}
        else:
            return JSONResponse(
                {"ok": False, "error": r.text, "status_code": r.status_code},
                status_code=r.status_code
            )
@app.get("/api/proxy")
async def proxy_content(url: str, github_token: Optional[str] = Header(None)):
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
            print(f"Proxy error: {e}")
            raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")

# -------------------------------
# NEW: Commit File
# -------------------------------
@app.post("/api/commit-file")
async def commit_file(payload: dict):
    owner = payload.get("owner")
    repo = payload.get("repo")
    path = payload.get("path")
    content = payload.get("content")
    message = payload.get("message", "Update file via Dashboard")
    sha = payload.get("sha")
    branch = payload.get("branch") # Optional, defaults to default branch
    github_token = payload.get("github_token")
    
    if not all([owner, repo, path, content, sha, github_token]):
        raise HTTPException(status_code=400, detail="Missing required fields")
        
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    
    # Base64 encode content
    import base64
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
        r = await client.put(url, headers=headers, json=data)
        if r.status_code in [200, 201]:
            return {"ok": True, "msg": "File saved successfully", "new_sha": r.json()["content"]["sha"]}
        else:
            return JSONResponse(
                {"ok": False, "error": r.text, "status_code": r.status_code},
                status_code=r.status_code
            )

# -------------------------------
# NEW: Analyze Code (Full File)
# -------------------------------
@app.post("/api/analyze-code")
async def analyze_code_endpoint(payload: dict):
    code = payload.get("code")
    filename = payload.get("filename", "unknown.py")
    
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")
        
    from app.agents import analyze_full_code
    
    analysis = analyze_full_code(code, filename)
    return {"ok": True, "analysis": analysis}

# -------------------------------
# NEW: Auto-Fix Endpoint
# -------------------------------
@app.post("/api/auto-fix")
async def auto_fix_endpoint(payload: dict):
    owner = payload.get("owner")
    repo = payload.get("repo")
    branch = payload.get("branch")
    filename = payload.get("filename")
    code = payload.get("code")
    issues = payload.get("issues", [])
    github_token = payload.get("github_token")

    if not all([owner, repo, branch, filename, code, github_token]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    from app.agents import auto_fix_and_push
    
    result = auto_fix_and_push(owner, repo, branch, filename, code, issues, github_token)
    return result

# -------------------------------
# NEW: Push to Branch (Pushing Agent)
# -------------------------------
@app.post("/api/push-to-branch")
async def push_to_branch(payload: dict):
    """
    Pushing agent: Commits file content to a specific branch.
    """
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
    
    # Use the pushing agent
    from app.agents import push_file_to_branch
    
    result = await push_file_to_branch(
        owner, repo, path, content, message, sha, branch, github_token
    )
    
    return result

# -------------------------------
# NEW: Generate Single Fix Endpoint
# -------------------------------
@app.post("/api/generate-fix")
async def generate_fix_endpoint(payload: dict):
    code = payload.get("code")
    issue = payload.get("issue")
    
    if not code or not issue:
        raise HTTPException(status_code=400, detail="Missing code or issue")
        
    from app.agents import generate_fix_for_issue
    
    result = generate_fix_for_issue(code, issue)
    return result

# Serve Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

import json
from pathlib import Path

# -------------------------------
# Persistence Logic
# -------------------------------
DATA_DIR = Path("data")
DATA_FILE = DATA_DIR / "analysis_results.json"

def load_data():
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text())
    except Exception as e:
        print(f"Error loading data: {e}")
        return []

def save_data(data):
    try:
        DATA_DIR.mkdir(exist_ok=True)
        DATA_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error saving data: {e}")

# -------------------------------
# In-Memory Store for Analysis Results
# -------------------------------
analysis_results = load_data()

# -------------------------------
# API Endpoints for Dashboard
# -------------------------------
@app.get("/api/analysis")
async def get_analysis_results():
    """
    Enhanced activity logs with recent commits and file changes
    """
    return JSONResponse({"results": analysis_results})

@app.get("/api/activity-logs")
async def get_activity_logs(github_token: Optional[str] = Header(None)):
    """
    Get latest activity logs including commits and file changes
    """
    if not github_token:
        # Return stored analysis results only if no token
        return JSONResponse({
            "commits": [],
            "fileChanges": [],
            "analyses": analysis_results[:10]  # Last 10 analyses
        })
    
    try:
        # Fetch recent commits from all repos
        commits = []
        file_changes = []
        
        # Get user repos
        repos_url = "https://api.github.com/user/repos"
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github+json"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch repos
            repos_res = await client.get(repos_url, headers=headers, params={"sort": "updated", "per_page": 10})
            if repos_res.status_code == 200:
                repos = repos_res.json()
                
                # For each repo, get recent commits
                for repo in repos[:5]:  # Limit to 5 most recently updated repos
                    owner = repo["owner"]["login"]
                    repo_name = repo["name"]
                    
                    # Get latest commits
                    commits_url = f"https://api.github.com/repos/{owner}/{repo_name}/commits"
                    commits_res = await client.get(commits_url, headers=headers, params={"per_page": 3})
                    
                    if commits_res.status_code == 200:
                        repo_commits = commits_res.json()
                        for commit in repo_commits:
                            commits.append({
                                "sha": commit["sha"][:7],
                                "message": commit["commit"]["message"].split('\n')[0],  # First line only
                                "author": commit["commit"]["author"]["name"],
                                "date": commit["commit"]["author"]["date"],
                                "repo": f"{owner}/{repo_name}",
                                "url": commit["html_url"]
                            })
                    
                    # Get recent PRs to track file changes
                    prs_url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls"
                    prs_res = await client.get(prs_url, headers=headers, params={"state": "all", "per_page": 2, "sort": "updated"})
                    
                    if prs_res.status_code == 200:
                        prs = prs_res.json()
                        for pr in prs:
                            pr_number = pr["number"]
                            # Get PR files
                            files_url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls/{pr_number}/files"
                            files_res = await client.get(files_url, headers=headers, params={"per_page": 5})
                            
                            if files_res.status_code == 200:
                                files = files_res.json()
                                for file in files:
                                    file_changes.append({
                                        "filename": file["filename"],
                                        "status": file["status"],
                                        "additions": file["additions"],
                                        "deletions": file["deletions"],
                                        "changes": file["changes"],
                                        "pr_number": pr_number,
                                        "repo": f"{owner}/{repo_name}",
                                        "pr_title": pr["title"]
                                    })
        
        # Sort by recency
        commits = sorted(commits, key=lambda x: x["date"], reverse=True)[:15]
        file_changes = file_changes[:15]  # Limit to 15 most recent changes
        
        return JSONResponse({
            "commits": commits,
            "fileChanges": file_changes,
            "analyses": analysis_results[:10]
        })
        
    except Exception as e:
        logger.error(f"Failed to fetch activity logs: {str(e)}")
        return JSONResponse({
            "commits": [],
            "fileChanges": [],
            "analyses": analysis_results[:10],
            "error": str(e)
        })


# -------------------------------
# Dashboard Page
# -------------------------------
# (Already defined above)

@app.get("/")
async def read_index():
    return FileResponse("static/login.html")

@app.get("/login")
async def login_alias():
    return FileResponse("static/login.html")



