import os
import json
import tempfile
import subprocess
import logging
from typing import List, Dict, Any
import requests

# Import AI Orchestrator for multi-model support
from app.ai_orchestrator import generate_content

# Logging Setup
logger = logging.getLogger("ReviewEngine")
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(handler)


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

def run_multi_agent_review(files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Complete pipeline: reconstruct files, run lint, run AI review.
    Uses AI orchestrator with automatic Grok->Gemini failover.
    """

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
        logger.info("🤖 Running multi-agent code review")
        
        # Use orchestrator with JSON response format
        response_text = generate_content(prompt, response_format="json")
        result = json.loads(response_text)

      
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



# Enhanced Chat Engine with Code Modification Detection

def chat_with_agent(message: str, context: Dict[str, Any], history: List[Dict[str, str]]):
    """
    Enhanced conversational helper with intelligent code modification detection.
    
    Features:
    - Detects when user wants code changes
    - Detects when user wants to push/commit code
    - Automatically applies requested modifications
    - Returns both explanation and modified code
    
    Returns:
        dict: {
            "response": str (explanation),
            "code_modified": bool,
            "modified_code": str (if applicable),
            "filename": str (if applicable),
            "push_requested": bool (if user wants to commit/push),
            "commit_message": str (suggested commit message)
        }
    """
    
    # Step 1: Check if user wants to push/commit code
    if _detect_push_intent(message):
        logger.info("📤 Push/commit request detected")
        
        current_file = context.get("current_file", {})
        filename = current_file.get("filename", "")
        code = current_file.get("content", "")
        
        if not code or not filename:
            return {
                "response": "⚠️ No code to push. Please make sure you have a file open with changes.",
                "push_requested": False
            }
        
        # Generate a smart commit message based on the user's request
        commit_msg = _generate_commit_message(message, filename, context)
        
        return {
            "response": f"🚀 **Ready to Push**\n\nI'll commit `{filename}` to the branch.\n\n**Suggested commit message:**\n```\n{commit_msg}\n```\n\nInitiating push...",
            "push_requested": True,
            "commit_message": commit_msg,
            "code_modified": False
        }
    
    # Step 2: Detect if this is a code modification request
    current_file = context.get("current_file", {})
    filename = current_file.get("filename", "")
    original_code = current_file.get("content", "")
    
    is_code_change_request = _detect_code_change_intent(message)
    
    if is_code_change_request and original_code:
        logger.info("🔧 Code modification request detected")
        # Generate the modified code
        result = _apply_user_requested_changes(message, original_code, filename, context, history)
        return result
    else:
        # Regular chat response (no code modification)
        logger.info("💬 Regular chat response")
        sys_prompt = f"""
You are an AI coding assistant helping with PR review.
Here is the PR analysis context:

{json.dumps(context, indent=2)}

IMPORTANT INSTRUCTIONS:
1. Provide helpful explanations and suggestions.
2. Be concise and professional.
3. If discussing code, use markdown code blocks.
4. DO NOT wrap your response in JSON format.

Respond directly to the user's question or request.
"""

        full_prompt = sys_prompt + "\nConversation:\n"
        
        for msg in history:
            full_prompt += f"{msg['role'].upper()}: {msg['content']}\n"
        
        full_prompt += f"USER: {message}\nAI:"
        
        try:
            response_text = generate_content(full_prompt)
            return {
                "response": response_text,
                "code_modified": False,
                "push_requested": False
            }
        except Exception as e:
            return {
                "response": f"Error: {str(e)}",
                "code_modified": False,
                "push_requested": False
            }


def _detect_code_change_intent(message: str) -> bool:
    """
    Detect if user message is requesting code changes.
    Uses keywords and patterns to identify modification requests.
    """
    message_lower = message.lower()
    
    # Keywords that indicate code modification intent
    change_keywords = [
        "change", "modify", "update", "fix", "add", "remove", "delete",
        "replace", "refactor", "improve", "optimize", "correct",
        "make it", "can you", "please", "edit", "adjust", "tweak",
        "insert", "append", "prepend", "rename"
    ]
    
    code_keywords = [
        "code", "function", "class", "variable", "line", "file",
        "h1", "h2", "div", "button", "import", "def", "const", "let"
    ]
    
    # Check if message contains both action and code keywords
    has_change_keyword = any(keyword in message_lower for keyword in change_keywords)
    has_code_keyword = any(keyword in message_lower for keyword in code_keywords)
    
    return has_change_keyword or has_code_keyword


def _detect_push_intent(message: str) -> bool:
    """
    Detect if user wants to push/commit code to the branch.
    """
    message_lower = message.lower()
    
    push_keywords = [
        "push", "commit", "save", "deploy", "publish",
        "push it", "commit it", "commit this", "push this",
        "save to branch", "save changes", "push to branch",
        "commit to branch", "push code", "commit code"
    ]
    
    return any(keyword in message_lower for keyword in push_keywords)


def _generate_commit_message(user_message: str, filename: str, context: Dict[str, Any]) -> str:
    """
    Generate an intelligent commit message based on user's request.
    """
    # Try to extract intent from user message
    message_lower = user_message.lower()
    
    # Common patterns
    if "fix" in message_lower:
        return f"fix: Updates to {filename}"
    elif "add" in message_lower or "new" in message_lower:
        return f"feat: Add changes to {filename}"
    elif "update" in message_lower or "improve" in message_lower:
        return f"chore: Update {filename}"
    elif "refactor" in message_lower:
        return f"refactor: Refactor {filename}"
    elif "remove" in message_lower or "delete" in message_lower:
        return f"chore: Remove code from {filename}"
    else:
        # Default commit message
        return f"chore: AI-assisted changes to {filename}"



def _apply_user_requested_changes(
    user_request: str,
    original_code: str,
    filename: str,
    context: Dict[str, Any],
    history: List[Dict[str, str]]
) -> Dict[str, Any]:
    """
    Apply user-requested changes to code using AI.
    
    Returns:
        dict with response, modified code, and metadata
    """
    
    prompt = f"""
You are a Senior Software Engineer helping a developer make specific code changes.

CURRENT FILE: {filename}

ORIGINAL CODE:
```
{original_code}
```

USER REQUEST: {user_request}

CONTEXT (if relevant):
{json.dumps(context, indent=2)}

TASK:
1. Understand the user's specific request
2. Apply ONLY the changes they requested (be surgical, don't rewrite everything)
3. Maintain code style and existing patterns
4. Ensure the code remains functional

OUTPUT FORMAT (IMPORTANT - You must output valid JSON):
{{
    "explanation": "Brief explanation of what you changed (2-3 sentences)",
    "modified_code": "The complete modified code file",
    "changes_summary": "List of specific changes made (bullet points)"
}}

IMPORTANT: Return ONLY valid JSON. No markdown, no extra text.
"""
    
    try:
        logger.info(f"🤖 Applying changes to {filename}")
        response_text = generate_content(prompt, response_format="json")
        
        # Parse the JSON response
        result = json.loads(response_text)
        
        return {
            "response": f"✅ **Changes Applied**\n\n{result.get('explanation', '')}\n\n**Changes:**\n{result.get('changes_summary', '')}",
            "code_modified": True,
            "modified_code": result.get("modified_code", original_code),
            "filename": filename
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}")
        # Fallback: try to extract code from markdown blocks
        import re
        code_blocks = re.findall(r'```(?:\w+)?\n(.*?)```', response_text, re.DOTALL)
        
        if code_blocks:
            return {
                "response": "✅ **Changes Applied** (extracted from response)",
                "code_modified": True,
                "modified_code": code_blocks[0].strip(),
                "filename": filename
            }
        else:
            return {
                "response": f"⚠️ Could not parse the AI response. Here's what I got:\n\n{response_text}",
                "code_modified": False
            }
            
    except Exception as e:
        logger.error(f"Error applying changes: {str(e)}")
        return {
            "response": f"❌ Error applying changes: {str(e)}",
            "code_modified": False
        }



# Full File Deep Review

def analyze_full_code(code: str, filename: str) -> Dict[str, Any]:
    """Analyze code using AI orchestrator with automatic failover"""

    prompt = f"""
Deep full-file code review.

File: {filename}

Code:
{code}

IMPORTANT: You MUST respond with valid JSON only. No markdown, no explanations outside JSON.

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
        logger.info(f"🔍 Analyzing {filename}")
        response_text = generate_content(prompt, response_format="json")
        
        # Try to parse JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract JSON from the response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                # Fallback: return the text as a single issue
                return {
                    "summary": "Analysis completed (non-JSON response)",
                    "issues": [{
                        "category": "AI Response",
                        "severity": "Medium",
                        "line": 0,
                        "message": response_text[:500],  # First 500 chars
                        "suggestion": "Review the full AI response"
                    }],
                    "recommendation": "Review"
                }

    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        return {
            "summary": "AI Error",
            "issues": [{
                "category": "System", 
                "severity": "High", 
                "message": str(e)
            }],
            "recommendation": "Error"
        }


# Auto-Fix & Push Agent
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
        logger.info("🔧 Generating auto-fix")
        response_text = generate_content(prompt)
        fixed_code = response_text.replace("```python", "").replace("```", "").strip()
        
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

def generate_fix_for_issue(code: str, issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates a fix for a specific issue without pushing.
    Returns the full modified code.
    Uses AI orchestrator with automatic failover.
    """

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
        logger.info("🔧 Generating single issue fix")
        response_text = generate_content(prompt)
        fixed_code = response_text.replace("```python", "").replace("```", "").strip()
        
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
    Automatically fetches the latest SHA from the branch to prevent SHA mismatch errors.
    """
    import httpx
    import base64
    
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Fetch the latest SHA from the branch
            logger.info(f"📥 Fetching latest SHA for {path} from branch {branch}")
            get_response = await client.get(url, headers=headers, params={"ref": branch})
            
            current_sha = None
            if get_response.status_code == 200:
                current_sha = get_response.json().get("sha")
                logger.info(f"✓ Found current SHA: {current_sha}")
            elif get_response.status_code == 404:
                # File doesn't exist yet (new file)
                logger.info(f"⚠️ File {path} doesn't exist on branch {branch}, creating new file")
            else:
                logger.warning(f"⚠️ Failed to fetch current SHA (status {get_response.status_code}), attempting with provided SHA")
                current_sha = sha
            
            # Use fetched SHA if available, otherwise fall back to provided SHA
            final_sha = current_sha if current_sha else sha
            
            # Step 2: Prepare the file content
            content_bytes = content.encode('utf-8')
            base64_content = base64.b64encode(content_bytes).decode('utf-8')
            
            # Step 3: Push the file
            data = {
                "message": message,
                "content": base64_content,
                "branch": branch
            }
            
            # Only include SHA if we have one (for updates, not new files)
            if final_sha:
                data["sha"] = final_sha
            
            logger.info(f"📤 Pushing {path} to branch {branch}")
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
