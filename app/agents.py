import os
import json
import tempfile
import subprocess
import logging
from typing import List, Dict, Any
import requests
import google.generativeai as genai
import time
import random
from functools import wraps
from google.api_core import exceptions as google_exceptions

# Logging Setup

logger = logging.getLogger("ReviewEngine")
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(handler)


# Gemini API 
GENAI_API_KEY = os.getenv("GEMINI_API_KEY")
if GENAI_API_KEY:
    genai.configure(api_key=GENAI_API_KEY)


def retry_with_backoff(retries=3, initial_delay=1.0, backoff_factor=2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for i in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except google_exceptions.ResourceExhausted as e:
                    if i == retries:
                        logger.error(f"Quota exceeded after {retries} retries: {e}")
                        raise e
                    
                    sleep_time = delay + random.uniform(0, 0.1) 
                    logger.warning(f"Quota exceeded. Retrying in {sleep_time:.2f}s (Attempt {i+1}/{retries})...")
                    time.sleep(sleep_time)
                    delay *= backoff_factor
                except Exception as e:
                   
                    raise e
        return wrapper
    return decorator


# GitHub Raw Content Fetcher

def fetch_raw_file(raw_url: str) -> str:
    """
    Fetches the raw file content from GitHub using raw_url.
    """
    try:
        logger.info(f"Fetching raw file from: {raw_url}")
        response = requests.get(raw_url)

        if response.status_code == 200:
            return response.text
        else:
            logger.warning(f"Unable to fetch file: {raw_url} [{response.status_code}]")
            return ""
    except Exception as e:
        logger.error(f"Error fetching raw file: {str(e)}")
        return ""



# Patch → File Rebuilder

def apply_patch_to_content(original: str, patch: str) -> str:
    """
    Uses 'git apply' to apply a unified diff to original text.
    """
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
          
            src_path = os.path.join(temp_dir, "temp_file")
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(original)

           
            
            patch_header = f"--- a/temp_file\n+++ b/temp_file\n"
            full_patch = patch_header + patch
            
            patch_path = os.path.join(temp_dir, "patch.diff")
            with open(patch_path, "w", encoding="utf-8") as f:
                f.write(full_patch)

           
            cmd = ["git", "apply", "--ignore-space-change", "--ignore-whitespace", "patch.diff"]
            
            subprocess.run(cmd, cwd=temp_dir, check=True, capture_output=True, text=True)

            
            if os.path.exists(src_path):
                with open(src_path, "r", encoding="utf-8") as f:
                    return f.read()

    except subprocess.CalledProcessError as e:
        logger.error(f"Git apply failed: {e.stderr}")
        return None
    except Exception as e:
        logger.error(f"Patch application failed: {str(e)}")
        return None

    return original


# Linting Engine

def run_linter(file_content: str, filename: str) -> List[Dict[str, Any]]:
    """
    Runs pylint on the fully reconstructed file.
    """
    if not filename.endswith(".py"):
        return []

    issues = []

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["pylint", "--output-format=json", tmp_path],
            capture_output=True,
            text=True
        )

        if result.stdout:
            try:
                lint_errors = json.loads(result.stdout)

                for error in lint_errors:
                    issues.append({
                        "category": "Linting",
                        "severity": error.get("type", "info"),
                        "file": filename,
                        "line": error.get("line", 0),
                        "message": f"{error.get('symbol')}: {error.get('message')}",
                        "suggestion": "Fix linting error"
                    })

            except json.JSONDecodeError:
                logger.error("Pylint returned invalid JSON.")

    finally:
        try:
            os.remove(tmp_path)
        except:
            pass

    return issues



# Multi-Agent AI Review

@retry_with_backoff(retries=3, initial_delay=2.0)
def run_multi_agent_review(files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Complete pipeline: reconstruct files, run lint, run AI review.
    """

    if not GENAI_API_KEY:
        return {
            "summary": "Missing API Key",
            "issues": [{"category": "System", "severity": "High", "message": "Gemini API key missing."}],
            "recommendation": "Manual Review Required"
        }

    diff_context = ""
    all_issues = []

    for f in files:
        filename = f.get("filename")
        patch = f.get("patch", "")
        raw_url = f.get("raw_url", "")

        original_content = fetch_raw_file(raw_url) if raw_url else ""

        reconstructed = apply_patch_to_content(original_content, patch)

        if reconstructed:
            lint_issues = run_linter(reconstructed, filename)
            all_issues.extend(lint_issues)
        else:
            logger.warning(f"Skipping linter for {filename} due to patch failure.")

        if len(patch) > 10000:
            patch = patch[:10000] + "\n... (truncated)"

        diff_context += f"File: {filename}\nDiff:\n{patch}\n\n"

    prompt = f"""
You are a Principal Software Architect orchestrating a Multi-Agent Code Review.
You have been asked to review the following code changes (Diffs).

### The Agents
You must simulate the following four distinct expert personas. Each agent should analyze the code from their specific perspective ONLY.

1.  **Logic Expert **:
    - Focus: Correctness, business logic, race conditions, edge cases, error handling.
    - Look for: Off-by-one errors, incorrect conditions, unhandled exceptions, wrong assumptions.

2.  **Security Auditor **:
    - Focus: Vulnerabilities, data protection, authentication, authorization.
    - Look for: SQL injection, XSS, sensitive data exposure, missing checks, unsafe inputs.

3.  **Performance Engineer **:
    - Focus: Efficiency, scalability, resource usage.
    - Look for: N+1 queries, expensive loops, memory leaks, unoptimized algorithms.

4.  **Clean Code Reviewer **:
    - Focus: Readability, maintainability, style, best practices.
    - Look for: Naming conventions, function length, code duplication (DRY), SOLID principles.

### The Code Changes
{diff_context}

### Output Format
You must output a valid JSON object with the following structure.
IMPORTANT: Do not include markdown formatting (like ```json). Just the raw JSON.

{{
    "summary": "A concise executive summary of the review (max 3 sentences).",
    "issues": [
        {{
            "category": "Logic",
            "severity": "Critical|High|Medium|Low",
            "file": "filename",
            "line": <line_number_from_diff_hunk_if_possible_else_0>,
            "message": "Specific issue description.",
            "suggestion": "Actionable fix or code snippet."
        }},
        {{
            "category": "Security",
            ...
        }}
    ],
    "recommendation": "Approve | Request Changes | Comment"
}}
"""

    try:
        print("DEBUG: Initializing Gemini Model: gemini-2.5-flash")
        model = genai.GenerativeModel("gemini-2.5-flash")

        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )

        result = json.loads(response.text)

      
        all_issues.extend(result.get("issues", []))

      
        categorized_result = {
            "summary": result.get("summary", "Analysis complete."),
            "recommendation": result.get("recommendation", "Review"),
            "linter": [],
            "security": [],
            "performance": [],
            "issues": [] 
        }

        for issue in all_issues:
            cat = issue.get("category", "").lower()
            
            if "lint" in cat:
                categorized_result["linter"].append(issue)
            elif any(x in cat for x in ["security", "vulnerability", "auth", "injection", "xss", "safe"]):
                categorized_result["security"].append(issue)
            elif any(x in cat for x in ["performance", "efficiency", "scalability", "memory", "speed", "optimiz"]):
                categorized_result["performance"].append(issue)
            else:
                
                categorized_result["issues"].append(issue)

        return categorized_result

    except Exception as e:
        return {
            "summary": "AI Error",
            "issues": [{"category": "System", "severity": "High", "message": str(e)}],
            "recommendation": "Manual Review Required"
        }



# Chat Engine

@retry_with_backoff(retries=3, initial_delay=2.0)
def chat_with_agent(message: str, context: Dict[str, Any], history: List[Dict[str, str]]):
    """
    A conversational helper for discussing PR analysis.
    """

    if not GENAI_API_KEY:
        return "API key missing."

    sys_prompt = f"""
You are an AI coding assistant helping with PR review.
Here is the PR analysis context:

{json.dumps(context, indent=2)}

You have access to the code in the 'context' field.
If the user asks to modify code (e.g., "add an h1 tag", "fix this bug"), you should:
1. Generate the corrected code snippet or the full file content if appropriate.
2. Wrap the code in markdown code blocks (e.g., ```html ... ```).
3. Explain your changes briefly.

Respond concisely and professionally.
"""

    full_prompt = sys_prompt + "\nConversation:\n"

    for msg in history:
        full_prompt += f"{msg['role'].upper()}: {msg['content']}\n"

    full_prompt += f"USER: {message}\nAI:"    

    try:
        print("DEBUG: Initializing Gemini Model: gemini-2.5-flash")
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(full_prompt)
        return response.text

    except Exception as e:
        return f"Error: {str(e)}"



# Full File Deep Review

@retry_with_backoff(retries=3, initial_delay=2.0)
def analyze_full_code(code: str, filename: str) -> Dict[str, Any]:
    if not GENAI_API_KEY:
        return {"summary": "Missing key", "issues": [], "recommendation": "Error"}

    prompt = f"""
Deep full-file code review.

File: {filename}

Code:
{code}

Output JSON:
{{
  "summary": "Brief summary of code quality",
  "issues": [
    {{
      "category": "Logic|Security|Performance|Style",
      "severity": "High|Medium|Low",
      "line": <line_number>,
      "message": "Description of the issue",
      "suggestion": "How to fix it"
    }}
  ],
  "recommendation": "Approve|Refactor"
}}
"""

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)

    except Exception as e:
        return {
            "summary": "AI Error",
            "issues": [{"category": "System", "severity": "High", "message": str(e)}],
            "recommendation": "Error"
        }


# Auto-Fix & Push Agent
@retry_with_backoff(retries=3, initial_delay=2.0)
def auto_fix_and_push(
    owner: str, 
    repo: str, 
    branch: str, 
    filename: str, 
    original_code: str, 
    issues: List[Dict[str, Any]], 
    github_token: str
) -> Dict[str, Any]:
    """
    Uses AI to fix the code based on issues and pushes it to the branch.
    """
    if not GENAI_API_KEY:
        return {"ok": False, "error": "Missing Gemini API Key"}


    prompt = f"""
You are a Senior Software Engineer tasked with fixing code issues.

File: {filename}

Issues to Fix:
{json.dumps(issues, indent=2)}

Original Code:
{original_code}

Task:
1. Apply fixes for the listed issues.
2. Ensure the code remains functional and follows best practices.
3. Return ONLY the full fixed code. No markdown formatting, no explanations.
"""

    try:
        print("DEBUG: Initializing Gemini Model (Fix): gemini-2.5-flash")
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        fixed_code = response.text.replace("```python", "").replace("```", "").strip()
        
        if not fixed_code:
             return {"ok": False, "error": "AI generated empty code"}

    except Exception as e:
        return {"ok": False, "error": f"AI Generation Failed: {str(e)}"}

   
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{filename}"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }

    
    sha = None
    try:
        get_res = requests.get(url, headers=headers, params={"ref": branch})
        if get_res.status_code == 200:
            sha = get_res.json().get("sha")
    except Exception as e:
        logger.error(f"Failed to fetch SHA: {e}")

    
    import base64
    content_bytes = fixed_code.encode('utf-8')
    base64_content = base64.b64encode(content_bytes).decode('utf-8')

    data = {
        "message": f"AI Auto-Fix for {filename}",
        "content": base64_content,
        "branch": branch
    }
    if sha:
        data["sha"] = sha

    try:
        put_res = requests.put(url, headers=headers, json=data)
        if put_res.status_code in [200, 201]:
            return {"ok": True, "msg": "Fix applied and pushed successfully", "new_sha": put_res.json()["content"]["sha"]}
        else:
            return {"ok": False, "error": f"GitHub Push Failed: {put_res.text}"}
    except Exception as e:
        return {"ok": False, "error": f"Network Error: {str(e)}"}


# Single Issue Fix Generator

@retry_with_backoff(retries=3, initial_delay=2.0)
def generate_fix_for_issue(code: str, issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates a fix for a specific issue without pushing.
    Returns the full modified code.
    """
    if not GENAI_API_KEY:
        return {"ok": False, "error": "Missing Gemini API Key"}

    prompt = f"""
You are a Senior Software Engineer.
Fix the following specific issue in the code.

Issue:
{json.dumps(issue, indent=2)}

Code:
{code}

Task:
1. Apply the fix for the specific issue described.
2. Return ONLY the full fixed code. No markdown formatting, no explanations.
"""

    try:
        print("DEBUG: Initializing Gemini Model (Single Fix): gemini-2.5-flash")
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        fixed_code = response.text.replace("```python", "").replace("```", "").strip()
        
        if not fixed_code:
             return {"ok": False, "error": "AI generated empty code"}
             
        return {"ok": True, "fixed_code": fixed_code}

    except Exception as e:
        return {"ok": False, "error": f"AI Generation Failed: {str(e)}"}


# Pushing Agent

async def push_file_to_branch(
    owner: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    sha: str,
    branch: str,
    github_token: str
) -> Dict[str, Any]:
    """
    Pushing Agent: Commits a file to a GitHub branch.
    """
    import httpx
    import base64
    
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
        "sha": sha,
        "branch": branch
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.put(url, headers=headers, json=data)
            
            if r.status_code in [200, 201]:
                logger.info(f"✓ Pushed {path} to {branch}")
                return {
                    "ok": True,
                    "msg": f"File committed to {branch}",
                    "new_sha": r.json()["content"]["sha"],
                    "commit_url": r.json()["commit"]["html_url"]
                }
            else:
                logger.error(f"Push failed: {r.text}")
                return {
                    "ok": False,
                    "error": r.text,
                    "status_code": r.status_code
                }
    except Exception as e:
        logger.error(f"Network error during push: {str(e)}")
        return {"ok": False, "error": f"Network error: {str(e)}"}
