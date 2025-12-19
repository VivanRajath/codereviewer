const GITHUB_API_BASE = 'https://api.github.com';

// Helper to get token
function getToken() {
    return localStorage.getItem('gh_token');
}

// Helper for headers
function getHeaders() {
    const token = getToken();
    return {
        'Authorization': `token ${token}`,
        'Accept': 'application/vnd.github.v3+json'
    };
}

// Login & Initialization Logic
document.addEventListener('DOMContentLoaded', () => {
    // Check for OAuth token in URL hash (Global check for dashboard redirect)
    const hash = window.location.hash;
    if (hash && hash.includes('token=')) {
        const token = hash.split('token=')[1];
        if (token) {
            // Verify token by fetching user
            fetch(`${GITHUB_API_BASE}/user`, {
                headers: {
                    'Authorization': `token ${token}`,
                    'Accept': 'application/vnd.github.v3+json'
                }
            })
                .then(res => {
                    if (res.ok) return res.json();
                    throw new Error('Invalid token');
                })
                .then(user => {
                    localStorage.setItem('gh_token', token);
                    localStorage.setItem('gh_user', JSON.stringify(user));

                    // Update UI if on dashboard
                    if (document.getElementById('userName')) {
                        document.getElementById('userName').textContent = user.login;
                    }
                    if (document.getElementById('userLogin')) {
                        document.getElementById('userLogin').textContent = '@' + user.login;
                    }
                    if (document.getElementById('userAvatar')) {
                        document.getElementById('userAvatar').src = user.avatar_url;
                    }

                    // If we are on login page, go to dashboard. 
                    // If we are already on dashboard, just clear the hash
                    if (window.location.pathname === '/' || window.location.pathname === '/login') {
                        window.location.href = '/dashboard';
                    } else {
                        // Clean URL
                        window.history.replaceState(null, null, window.location.pathname);
                        // Reload specific dashboard elements if needed
                        if (typeof window.fetchActivityLogs === 'function') {
                            window.fetchActivityLogs();
                        }
                    }
                })
                .catch(err => {
                    console.error(err);
                    if (window.location.pathname === '/dashboard') {
                        alert('Authentication failed: ' + err.message);
                    }
                });
        }
    }

    // Manual login form logic
    if (document.getElementById('loginForm')) {
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const token = document.getElementById('token').value.trim();
            const btn = document.getElementById('loginBtn');
            const spinner = document.getElementById('loginSpinner');
            const errorDiv = document.getElementById('loginError');
            const btnText = btn.querySelector('.btn-text');

            if (!token) return;

            btn.disabled = true;
            if (btnText) btnText.classList.add('hidden');
            if (spinner) spinner.classList.remove('hidden');
            if (errorDiv) errorDiv.classList.add('hidden');

            try {
                const res = await fetch(`${GITHUB_API_BASE}/user`, {
                    headers: {
                        'Authorization': `token ${token}`,
                        'Accept': 'application/vnd.github.v3+json'
                    }
                });

                if (res.ok) {
                    const user = await res.json();
                    localStorage.setItem('gh_token', token);
                    localStorage.setItem('gh_user', JSON.stringify(user));
                    window.location.href = '/dashboard';
                } else {
                    throw new Error('Invalid token');
                }
            } catch (err) {
                if (errorDiv) {
                    errorDiv.textContent = err.message || 'Failed to login';
                    errorDiv.classList.remove('hidden');
                }
                btn.disabled = false;
            }
        });
    }

    // Initialize sidebar user info and logout on all dashboard pages
    initializeSidebarUser();
    setupLogoutHandler();
});

// Initialize sidebar with user info
function initializeSidebarUser() {
    const user = JSON.parse(localStorage.getItem('gh_user') || '{}');
    if (user.login) {
        const userNameEl = document.getElementById('userName');
        const userLoginEl = document.getElementById('userLogin');
        const userAvatarEl = document.getElementById('userAvatar');

        if (userNameEl) userNameEl.textContent = user.login;
        if (userLoginEl) userLoginEl.textContent = '@' + user.login;
        if (userAvatarEl) userAvatarEl.src = user.avatar_url || '';
    }
}

// Setup unified logout handler
function setupLogoutHandler() {
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            localStorage.removeItem('gh_token');
            localStorage.removeItem('gh_user');
            window.location.href = '/';
        });
    }
}

// State
let currentRepo = null;
let currentPR = null;
let currentAnalysis = null;
let chatHistory = [];

// Monaco editor state
let monacoEditor = null;
let monacoRawModel = null;
let monacoWorkingModel = null;
let currentEditorMode = 'working';
let currentFileSha = null;
let currentFilePath = null;

// Create Monaco editor (called from inline script after Monaco is ready)
window.createMonacoEditor = function () {
    const el = document.getElementById('monacoEditor');
    if (!el || !window.monaco) return;

    monacoRawModel = monaco.editor.createModel('', 'plaintext');
    monacoWorkingModel = monaco.editor.createModel('', 'plaintext');

    monacoEditor = monaco.editor.create(el, {
        model: monacoWorkingModel,
        theme: 'vs-dark',
        automaticLayout: true,
        fontSize: 13,
        minimap: { enabled: false },
        fontFamily: "'JetBrains Mono', monospace"
    });

    // Default to reconstructed (working) mode
    setEditorMode('working');
};

// Editor language helper
function getLanguageFromFilename(filename) {
    if (!filename) return 'plaintext';
    if (filename.endsWith('.py')) return 'python';
    if (filename.endsWith('.js')) return 'javascript';
    if (filename.endsWith('.ts')) return 'typescript';
    if (filename.endsWith('.json')) return 'json';
    if (filename.endsWith('.css')) return 'css';
    if (filename.endsWith('.html')) return 'html';
    if (filename.endsWith('.md')) return 'markdown';
    return 'plaintext';
}

function setEditorMode(mode) {
    if (!monacoEditor || !monacoRawModel || !monacoWorkingModel) return;

    currentEditorMode = mode;

    if (mode === 'raw') {
        monacoEditor.setModel(monacoRawModel);
        monacoEditor.updateOptions({ readOnly: true });
    } else {
        monacoEditor.setModel(monacoWorkingModel);
        monacoEditor.updateOptions({ readOnly: false });
    }
}

// Open Editor with File
window.openEditor = async function (url, filename, sha) {
    if (!monacoEditor || !monacoWorkingModel) {
        console.error("Monaco Editor not initialized");
        return;
    }

    // Ensure we are in the correct tab
    switchTab('files');

    // Update UI
    document.getElementById('editorFileName').textContent = filename;
    currentFilePath = filename;
    currentFileSha = sha;

    // Highlight active file in list
    document.querySelectorAll('.file-item').forEach(item => {
        item.classList.remove('active');
        if (item.textContent.includes(filename)) {
            item.classList.add('active');
        }
    });

    // Show loading state
    monacoWorkingModel.setValue('LOADING...');
    monacoEditor.updateOptions({ readOnly: true });

    // Reset Chat
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) {
        chatMessages.innerHTML = '<div style="color: var(--text-dim); text-align: center; margin-top: 1rem;">ANALYZING...</div>';
    }

    try {
        let content = '';
        if (url) {
            const res = await fetch('/api/fetch-file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    owner: currentRepo.owner,
                    repo: currentRepo.name,
                    path: filename,
                    ref: currentPR ? currentPR.head.sha : 'main', // Use PR head SHA
                    github_token: getToken()
                })
            });

            if (res.ok) {
                const data = await res.json();
                content = data.content;
            } else {
                throw new Error('Failed to fetch file content');
            }
        } else {
            content = "// NO_CONTENT_URL_PROVIDED";
        }

        monacoWorkingModel.setValue(content);
        monacoRawModel.setValue(content); // Update raw model too
        monacoEditor.updateOptions({ readOnly: false });

        // Set Language
        const lang = getLanguageFromFilename(filename);
        monaco.editor.setModelLanguage(monacoWorkingModel, lang);

        // Trigger Analysis automatically
        analyzeEditorCode();

    } catch (err) {
        console.error(err);
        monacoWorkingModel.setValue('// FAILED_TO_LOAD_FILE');
        monacoEditor.updateOptions({ readOnly: true });
    }
};

// Toggle Chat Panel
window.toggleChat = function () {
    const splitView = document.getElementById('prSplitView');
    if (splitView) {
        splitView.classList.toggle('chat-collapsed');
        // Resize editor
        if (monacoEditor) {
            setTimeout(() => monacoEditor.layout(), 300);
        }
    }
};

// Handle Chat Input
window.handleChatInput = function (event) {
    if (event.key === 'Enter') {
        sendChatMessage();
    }
};

// Send Chat Message (Enhanced with Code Modification Support)
window.sendChatMessage = async function () {
    const input = document.getElementById('chatInput');
    const messagesDiv = document.getElementById('chatMessages');
    const message = input.value.trim();

    if (!message) return;

    // Add User Message
    messagesDiv.innerHTML += `
        <div class="chat-message user">
            ${message}
        </div>
    `;
    input.value = '';
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    // Add Loading Message
    const loadingId = 'loading-' + Date.now();
    messagesDiv.innerHTML += `
        <div id="${loadingId}" class="chat-message ai">
            <span class="typing-indicator">●●●</span>
        </div>
    `;
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    try {
        const code = monacoWorkingModel ? monacoWorkingModel.getValue() : '';

        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                context: {
                    current_file: {
                        filename: currentFilePath || 'unknown',
                        content: code
                    },
                    analysis: currentAnalysis
                },
                history: chatHistory
            })
        });

        const data = await res.json();

        // Remove loading
        const loadingEl = document.getElementById(loadingId);
        if (loadingEl) loadingEl.remove();

        // Check if push/commit was requested
        if (data.push_requested) {
            // Show AI response first
            messagesDiv.innerHTML += `
                <div class="chat-message ai" style="border-left: 3px solid var(--secondary-color);">
                    <div style="white-space: pre-wrap;">${data.response}</div>
                </div>
            `;
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

            // Execute the push
            await executePushToBranch(data.commit_message || 'AI-assisted changes');
        }
        // Check if code was modified
        else if (data.code_modified && data.modified_code) {
            // Update Monaco editor with modified code
            if (monacoWorkingModel) {
                monacoWorkingModel.setValue(data.modified_code);
            }

            // Show special response for code modifications
            messagesDiv.innerHTML += `
                <div class="chat-message ai" style="border-left: 3px solid var(--success-color);">
                    <div style="color: var(--success-color); font-weight: bold; margin-bottom: 0.5rem;">
                        CODE MODIFIED
                    </div>
                    <div style="white-space: pre-wrap;">${data.response}</div>
                    <div style="margin-top: 0.5rem; padding: 0.5rem; background: rgba(0,255,0,0.1); border-radius: 4px; font-size: 0.85rem;">
                        Changes applied to editor
                    </div>
                </div>
            `;
        } else {
            // Regular chat response (no code modification)
            messagesDiv.innerHTML += `
                <div class="chat-message ai">
                    <div style="white-space: pre-wrap;">${data.response}</div>
                </div>
            `;
        }

        // Update History
        chatHistory.push({ role: 'user', content: message });
        chatHistory.push({ role: 'assistant', content: data.response });

    } catch (err) {
        console.error(err);
        const loadingEl = document.getElementById(loadingId);
        if (loadingEl) {
            loadingEl.innerHTML = `<span style="color: var(--danger-color);">ERROR: FAILED_TO_SEND_MESSAGE</span>`;
        }
    }

    messagesDiv.scrollTop = messagesDiv.scrollHeight;
};

// Execute Push to Branch (called from chat when push is requested)
async function executePushToBranch(commitMessage) {
    const messagesDiv = document.getElementById('chatMessages');

    if (!currentPR || !currentFilePath || !currentFileSha || !monacoWorkingModel) {
        messagesDiv.innerHTML += `
            <div class="chat-message ai" style="color: var(--danger-color);">
                Cannot push: Missing PR, file, or editor context.
            </div>
        `;
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
        return;
    }

    // Create pushing status message
    const pushingId = 'pushing-' + Date.now();
    messagesDiv.innerHTML += `
        <div id="${pushingId}" class="chat-message ai" style="border-left: 3px solid var(--warning-color);">
            <div style="color: var(--warning-color); font-weight: bold;">
                PUSHING AGENT ACTIVATED
            </div>
            <div style="margin-top: 0.5rem;">
                <span class="typing-indicator">●●●</span> Pushing code to branch...
            </div>
        </div>
    `;
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    try {
        const code = monacoWorkingModel.getValue();
        const branch = currentPR.head.ref; // PR branch

        const result = await fetch('/api/push-to-branch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                owner: currentRepo.owner,
                repo: currentRepo.name,
                path: currentFilePath,
                content: code,
                message: commitMessage,
                sha: currentFileSha,
                branch: branch,
                github_token: getToken()
            })
        });

        const data = await result.json();

        // Remove pushing message
        const pushingEl = document.getElementById(pushingId);
        if (pushingEl) pushingEl.remove();

        if (data.ok) {
            // Success!
            messagesDiv.innerHTML += `
                <div class="chat-message ai" style="border-left: 3px solid var(--success-color);">
                    <div style="color: var(--success-color); font-weight: bold; margin-bottom: 0.5rem;">
                        CODE PUSHED SUCCESSFULLY
                    </div>
                    <div style="margin-top: 0.5rem;">
                        <div><strong>File:</strong> ${currentFilePath}</div>
                        <div><strong>Branch:</strong> ${branch}</div>
                        <div><strong>Commit:</strong> ${commitMessage}</div>
                        ${data.new_sha ? `<div><strong>SHA:</strong> <code>${data.new_sha.substring(0, 7)}</code></div>` : ''}
                        ${data.commit_url ? `<div style="margin-top: 0.5rem;"><a href="${data.commit_url}" target="_blank" style="color: var(--primary-color);">View Commit →</a></div>` : ''}
                    </div>
                </div>
            `;

            // Update current SHA for next push
            if (data.new_sha) {
                currentFileSha = data.new_sha;
            }
        } else {
            // Error
            messagesDiv.innerHTML += `
                <div class="chat-message ai" style="border-left: 3px solid var(--danger-color);">
                    <div style="color: var(--danger-color); font-weight: bold;">
                        PUSH FAILED
                    </div>
                    <div style="margin-top: 0.5rem;">
                        ${data.error || 'Unknown error occurred'}
                    </div>
                </div>
            `;
        }

        messagesDiv.scrollTop = messagesDiv.scrollHeight;

    } catch (err) {
        // Remove pushing message
        const pushingEl = document.getElementById(pushingId);
        if (pushingEl) pushingEl.remove();

        console.error('Push error:', err);
        messagesDiv.innerHTML += `
            <div class="chat-message ai" style="color: var(--danger-color);">
                Network error: ${err.message}
            </div>
        `;
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
}

// Helper function to extract analysis summary
function getAnalysisSummary(analysis) {
    if (!analysis) return 'NO_ANALYSIS_AVAILABLE';
    if (typeof analysis === 'string') return analysis;
    if (analysis.summary) return analysis.summary;
    if (analysis.message) return analysis.message;
    return 'ANALYSIS_COMPLETED';
}

// Fetch Activity Logs (Enhanced with commits and file changes)
let activityDataCache = null;
let lastFetchTime = 0;

window.fetchActivityLogs = async function (force = false) {
    const commitsGrid = document.getElementById('commitsGrid');
    const fileChangesGrid = document.getElementById('fileChangesGrid');
    const analysesGrid = document.getElementById('analysesGrid');

    // Use cache if data was fetched less than 30 seconds ago and not forced
    const now = Date.now();
    if (!force && activityDataCache && (now - lastFetchTime) < 30000) {
        renderActivityData(activityDataCache);
        return;
    }

    if (commitsGrid) commitsGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim);">LOADING_COMMITS...</div>';
    if (fileChangesGrid) fileChangesGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim);">LOADING_FILE_CHANGES...</div>';
    if (analysesGrid) analysesGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim);">LOADING_ANALYSES...</div>';

    try {
        const res = await fetch('/api/activity-logs', {
            headers: { 'github-token': getToken() }
        });
        const data = await res.json();

        // Cache the data
        activityDataCache = data;
        lastFetchTime = now;

        renderActivityData(data);

    } catch (err) {
        console.error('Failed to fetch activity logs', err);
        if (commitsGrid) commitsGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--danger-color);">SYSTEM_ERROR: FAILED_TO_FETCH_COMMITS</div>';
        if (fileChangesGrid) fileChangesGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--danger-color);">SYSTEM_ERROR: FAILED_TO_FETCH_FILE_CHANGES</div>';
        if (analysesGrid) analysesGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--danger-color);">SYSTEM_ERROR: FAILED_TO_FETCH_ANALYSES</div>';
    }
};

function renderActivityData(data) {
    const commitsGrid = document.getElementById('commitsGrid');
    const fileChangesGrid = document.getElementById('fileChangesGrid');
    const analysesGrid = document.getElementById('analysesGrid');

    // Display Commits
    if (commitsGrid) {
        if (!data.commits || data.commits.length === 0) {
            commitsGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim);">NO_RECENT_COMMITS_FOUND.</div>';
        } else {
            commitsGrid.innerHTML = data.commits.map(commit => `
                <div class="card" onclick="window.open('${commit.url}', '_blank')">
                    <div class="card-title">
                        <span style="font-family: monospace; color: var(--primary-color);">${commit.sha}</span>
                        <span class="status-badge status-open">${commit.repo}</span>
                    </div>
                    <div style="font-size: 0.9rem; color: var(--text-color); margin-top: 0.5rem;">
                        ${commit.message}
                    </div>
                    <div class="card-meta" style="margin-top: 0.5rem;">
                        AUTHOR: ${commit.author} | ${new Date(commit.date).toLocaleString()}
                    </div>
                </div>
            `).join('');
        }
    }

    // Display File Changes
    if (fileChangesGrid) {
        if (!data.fileChanges || data.fileChanges.length === 0) {
            fileChangesGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim);">NO_RECENT_FILE_CHANGES_FOUND.</div>';
        } else {
            fileChangesGrid.innerHTML = data.fileChanges.map(file => `
                <div class="card">
                    <div class="card-title">
                        <span>${file.filename}</span>
                        <span class="status-badge status-${file.status === 'added' ? 'open' : file.status === 'removed' ? 'closed' : 'open'}">${file.status}</span>
                    </div>
                    <div style="font-size: 0.9rem; color: var(--text-color); margin-top: 0.5rem;">
                        PR #${file.pr_number}: ${file.pr_title}
                    </div>
                    <div class="card-meta" style="margin-top: 0.5rem;">
                        REPO: ${file.repo} | 
                        <span style="color: var(--primary-color);">+${file.additions}</span> / 
                        <span style="color: var(--danger-color);">-${file.deletions}</span>
                    </div>
                </div>
            `).join('');
        }
    }

    // Display PR Analyses
    if (analysesGrid) {
        if (!data.analyses || data.analyses.length === 0) {
            analysesGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim);">NO_RECENT_ANALYSES_FOUND.</div>';
        } else {
            analysesGrid.innerHTML = data.analyses.map(item => `
                <div class="card" onclick='openAnalysisModal(${JSON.stringify(item).replace(/'/g, "&#39;")})'>
                    <div class="card-title">
                        <span>${item.repo} #${item.pr_number}</span>
                        <span class="status-badge status-open">${item.action || 'ANALYZED'}</span>
                    </div>
                    <div class="card-meta">
                        FILES: ${item.changed_files_count} | OWNER: ${item.owner}
                    </div>
                    <div style="font-size: 0.9rem; color: var(--text-color); overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; margin-top: 0.5rem;">
                        ${getAnalysisSummary(item.analysis)}
                    </div>
                </div>
            `).join('');
        }
    }
}

// Tab switching for activity dashboard
window.switchActivityTab = function (tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // Update tab content
    document.querySelectorAll('#activitySection .tab-content').forEach(content => {
        content.classList.remove('active');
    });
    const activeTab = document.getElementById(`tab-${tabName}`);
    if (activeTab) {
        activeTab.classList.add('active');
    }
};

// Keep old function for backward compatibility
window.fetchAnalysis = window.fetchActivityLogs;

// Save as Branch
async function openSaveBranchModal() {
    if (!currentPR) return;
    const branchName = prompt("ENTER_NEW_BRANCH_NAME:");
    if (!branchName) return;

    try {
        const res = await fetch('/api/save-branch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                owner: currentPR.owner,
                repo: currentPR.repo,
                base_branch: 'main',
                new_branch_name: branchName,
                github_token: getToken()
            })
        });
        const data = await res.json();
        if (data.ok) {
            alert(`BRANCH ${branchName} CREATED.`);
        } else {
            alert('FAILED_TO_CREATE_BRANCH: ' + (data.error || 'UNKNOWN_ERROR'));
        }
    } catch (err) {
        alert('NETWORK_ERROR');
    }
}

// Modal (For Activity Feed)
window.openAnalysisModal = function (item) {
    document.getElementById('modalTitle').textContent = `ANALYSIS: ${item.repo} #${item.pr_number}`;
    const contentDiv = document.getElementById('modalContent');
    contentDiv.innerHTML = '';

    const analysis = item.analysis;
    if (typeof analysis === 'string') {
        contentDiv.textContent = analysis;
    } else {
        const summary = document.createElement('div');
        summary.innerHTML = `<strong style="color: var(--primary-color);">SUMMARY:</strong> ${analysis.summary || 'NO_SUMMARY.'} <br><br> <strong style="color: var(--secondary-color);">RECOMMENDATION:</strong> ${analysis.recommendation || 'NO_RECOMMENDATION.'}`;
        summary.style.marginBottom = '1rem';
        contentDiv.appendChild(summary);

        if (analysis.issues) {
            analysis.issues.forEach(issue => {
                const el = document.createElement('div');
                el.style.marginBottom = '0.5rem';
                el.style.padding = '0.5rem';
                el.style.background = 'rgba(255, 255, 255, 0.05)';
                el.innerHTML = `<strong style="color: var(--primary-color);">${issue.category || 'ISSUE'}</strong>: ${issue.message || ''}`;
                contentDiv.appendChild(el);
            });
        }
    }

    document.getElementById('analysisModal').classList.add('show');
    document.getElementById('modalOverlay').classList.add('show');
};

window.closeModal = function () {
    const modal = document.getElementById('analysisModal');
    const overlay = document.getElementById('modalOverlay');
    if (modal) modal.classList.remove('show');
    if (overlay) overlay.classList.remove('show');
};

window.analyzeEditorCode = async function () {
    const analysisDiv = document.getElementById('chatMessages');
    if (!analysisDiv) return;

    if (!monacoWorkingModel) {
        // alert("EDITOR_NOT_READY"); // Silent fail or retry?
        return;
    }

    const code = monacoWorkingModel.getValue();
    // Use a loading bubble
    analysisDiv.innerHTML = `
        <div class="chat-message ai">
            ANALYZING CODE...
        </div>
    `;

    try {
        const res = await fetch('/api/analyze-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: code,
                filename: currentFilePath
            })
        });
        const data = await res.json();

        if (data.ok) {
            const analysis = data.analysis;
            window.currentEditorIssues = analysis.issues || []; // Store for auto-fix

            let html = '';
            if (analysis.issues && analysis.issues.length > 0) {
                const issuesHtml = analysis.issues.map((i, index) => {
                    const message = i.message || (typeof i === 'string' ? i : 'Unknown Issue');
                    return `
                    <div style="margin-bottom: 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 0.5rem;">
                        <div style="color: var(--warning-color); margin-bottom: 0.2rem;">> ${message}</div>
                        <div style="text-align: right;">
                            <button class="btn-sm" onclick="applyFix(${index})">APPLY FIX</button>
                        </div>
                    </div>
                `}).join('');

                html = `
                    <div class="chat-message ai">
                        <div style="font-weight: bold; margin-bottom: 0.5rem; color: var(--secondary-color);">ANALYSIS COMPLETE:</div>
                        ${issuesHtml}
                    </div>
                `;
            } else {
                html = `
                    <div class="chat-message ai" style="color: var(--success-color);">
                        NO ISSUES DETECTED.
                    </div>
                `;
            }
            analysisDiv.innerHTML = html;
        } else {
            analysisDiv.innerHTML = `
                <div class="chat-message ai" style="color: var(--danger-color);">
                    ANALYSIS_FAILED: ${data.detail || "UNKNOWN_ERROR"}
                </div>
            `;
        }
    }
    catch (e) {
        console.error(e);
        analysisDiv.innerHTML = `
            <div class="chat-message ai" style="color: var(--danger-color);">
                NETWORK_ERROR
            </div>
        `;
    }
};

window.applyFix = async function (index) {
    const issue = window.currentEditorIssues[index];
    if (!issue) return;

    const btn = document.querySelector(`button[onclick="applyFix(${index})"]`);
    if (btn) {
        btn.textContent = "APPLYING...";
        btn.disabled = true;
    }

    try {
        const code = monacoWorkingModel.getValue();
        const res = await fetch('/api/generate-fix', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: code,
                issue: issue
            })
        });
        const data = await res.json();

        if (data.ok) {
            monacoWorkingModel.setValue(data.fixed_code);
            if (btn) btn.textContent = "APPLIED";
            // Re-analyze to clear the issue
            // analyzeEditorCode(); // Optional: might be too aggressive
        } else {
            alert("FAILED_TO_APPLY_FIX: " + (data.error || "UNKNOWN"));
            if (btn) {
                btn.textContent = "APPLY FIX";
                btn.disabled = false;
            }
        }
    } catch (e) {
        console.error(e);
        alert("NETWORK_ERROR");
        if (btn) {
            btn.textContent = "APPLY FIX";
            btn.disabled = false;
        }
    }
};

// Auto-Fix File (analyzes if needed, then fixes sequentially)
window.autoFixFile = async function () {
    if (!monacoEditor || !monacoWorkingModel) {
        alert("EDITOR_NOT_READY.");
        return;
    }
    if (!currentRepo || !currentFilePath || !currentFileSha) {
        alert("NO_FILE_SELECTED.");
        return;
    }

    const btn = document.querySelector('button[onclick="autoFixFile()"]');
    const originalText = btn ? btn.textContent : "AUTO-FIX";
    if (btn) {
        btn.textContent = "ANALYZING...";
        btn.disabled = true;
    }

    let code = monacoWorkingModel.getValue();
    const chatMessages = document.getElementById('chatMessages');

    try {
        // Step 1: Analyze code first
        if (!window.currentEditorIssues || window.currentEditorIssues.length === 0) {
            const analyzeRes = await fetch('/api/analyze-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    code: code,
                    filename: currentFilePath
                })
            });
            const analyzeData = await analyzeRes.json();

            if (!analyzeData.ok || !analyzeData.analysis.issues || analyzeData.analysis.issues.length === 0) {
                alert("NO_ISSUES_FOUND_TO_FIX.");
                if (btn) {
                    btn.textContent = originalText;
                    btn.disabled = false;
                }
                return;
            }

            window.currentEditorIssues = analyzeData.analysis.issues;
        }

        const totalIssues = window.currentEditorIssues.length;

        // Step 2: Show To-Do List in Chatbot
        const todoId = 'autofix-todo-' + Date.now();
        if (chatMessages) {
            const todoMsg = document.createElement('div');
            todoMsg.id = todoId;
            todoMsg.className = 'chat-message ai';
            todoMsg.innerHTML = `
                <div style="color: var(--secondary-color); font-weight: bold; margin-bottom: 0.5rem;">
                    🔧 AUTO-FIX IN PROGRESS (${totalIssues} issues)
                </div>
                <div id="${todoId}-list" style="font-size: 0.9rem;">
                    ${window.currentEditorIssues.map((issue, idx) => {
                const message = issue.message || (typeof issue === 'string' ? issue : 'Unknown Issue');
                return `
                            <div id="${todoId}-item-${idx}" style="margin: 0.3rem 0; color: var(--text-dim);">
                                <span id="${todoId}-status-${idx}">⏳</span> ${message}
                            </div>
                        `;
            }).join('')}
                </div>
            `;
            chatMessages.appendChild(todoMsg);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        if (btn) btn.textContent = "FIXING...";

        // Step 3: Fix each issue sequentially
        let fixedCount = 0;
        for (let i = 0; i < window.currentEditorIssues.length; i++) {
            const issue = window.currentEditorIssues[i];

            // Update status to "fixing"
            const statusEl = document.getElementById(`${todoId}-status-${i}`);
            if (statusEl) statusEl.textContent = '🔄';

            try {
                // Get current code from editor
                code = monacoWorkingModel.getValue();

                // Generate fix for this specific issue
                const res = await fetch('/api/generate-fix', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        code: code,
                        issue: issue
                    })
                });
                const data = await res.json();

                if (data.ok && data.fixed_code) {
                    // Apply fix to editor
                    monacoWorkingModel.setValue(data.fixed_code);
                    code = data.fixed_code;

                    // Update status to "done"
                    if (statusEl) {
                        statusEl.textContent = '✅';
                        statusEl.parentElement.style.color = 'var(--success-color)';
                    }
                    fixedCount++;
                } else {
                    // Mark as failed
                    if (statusEl) {
                        statusEl.textContent = '❌';
                        statusEl.parentElement.style.color = 'var(--danger-color)';
                    }
                }
            } catch (e) {
                console.error('Fix failed for issue:', issue, e);
                if (statusEl) {
                    statusEl.textContent = '❌';
                    statusEl.parentElement.style.color = 'var(--danger-color)';
                }
            }

            // Small delay between fixes
            await new Promise(resolve => setTimeout(resolve, 300));
        }

        // Step 4: Show completion summary (no auto-commit)
        if (fixedCount > 0) {
            // Show success summary
            if (chatMessages) {
                const summaryMsg = document.createElement('div');
                summaryMsg.className = 'chat-message ai';
                summaryMsg.style.color = 'var(--primary-color)';
                summaryMsg.innerHTML = `
                    ✓ AUTO-FIX COMPLETE!
                    <br><br>
                    <strong>Fixed ${fixedCount} / ${totalIssues} issues in editor</strong>
                    <br>
                    <span style="color: var(--text-dim); font-size: 0.9rem;">
                        Review the changes and click "COMMIT & PUSH" when ready.
                    </span>
                `;
                chatMessages.appendChild(summaryMsg);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
        } else {
            alert("NO_FIXES_APPLIED");
        }

        // Clear issues cache
        window.currentEditorIssues = [];

    } catch (e) {
        console.error(e);
        alert("NETWORK_ERROR: " + e.message);
    } finally {
        if (btn) {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    }
};

// Commit Modal Variables
let commitResolve = null;
let commitReject = null;

// Show Commit Modal
function showCommitModal(defaultMessage) {
    return new Promise((resolve, reject) => {
        commitResolve = resolve;
        commitReject = reject;

        const modal = document.getElementById('commitModal');
        const input = document.getElementById('commitMessageInput');

        if (modal && input) {
            input.value = defaultMessage || '';
            modal.classList.add('show');
            setTimeout(() => input.focus(), 100);
        }
    });
}

// Close Commit Modal
window.closeCommitModal = function () {
    const modal = document.getElementById('commitModal');
    if (modal) modal.classList.remove('show');
    if (commitReject) commitReject(new Error('Cancelled'));
    commitResolve = null;
    commitReject = null;
};

// Confirm Commit
window.confirmCommit = function () {
    const input = document.getElementById('commitMessageInput');
    const message = input ? input.value.trim() : '';

    if (!message) {
        alert('Please enter a commit message');
        return;
    }

    const modal = document.getElementById('commitModal');
    if (modal) modal.classList.remove('show');

    if (commitResolve) commitResolve(message);
    commitResolve = null;
    commitReject = null;
};

// Handle Enter/Esc in commit input
window.handleCommitInputKeypress = function (event) {
    if (event.key === 'Enter') {
        confirmCommit();
    } else if (event.key === 'Escape') {
        closeCommitModal();
    }
};

// Commit and Push to Branch
window.commitAndPush = async function () {
    if (!monacoEditor || !monacoWorkingModel) {
        alert("EDITOR_NOT_READY.");
        return;
    }
    if (!currentRepo || !currentFilePath || !currentFileSha) {
        alert("NO_FILE_SELECTED.");
        return;
    }

    const btn = document.getElementById('commitPushBtn');
    const btnText = document.getElementById('commitBtnText');
    const spinner = document.getElementById('commitSpinner');

    const code = monacoWorkingModel.getValue();
    const message = prompt("Enter commit message:", `Update ${currentFilePath}`);

    if (!message) return;

    // Show loading state
    if (btn) btn.disabled = true;
    if (btnText) btnText.classList.add('hidden');
    if (spinner) spinner.classList.remove('hidden');

    // Get correct branch: PR branch > repo default > master > main
    const branch = currentPR
        ? (currentPR.head_branch || currentPR.base?.ref || 'master')
        : (currentRepo?.default_branch || 'master');

    try {
        const res = await fetch('/api/push-to-branch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                owner: currentRepo.owner,
                repo: currentRepo.name,
                path: currentFilePath,
                content: code,
                message: message,
                sha: currentFileSha,
                branch: branch,
                github_token: getToken()
            })
        });

        const data = await res.json();

        if (data.ok) {
            // Update SHA for next save
            currentFileSha = data.new_sha;

            // Show success
            if (btnText) btnText.textContent = '✓ PUSHED';
            if (btnText) btnText.classList.remove('hidden');
            if (spinner) spinner.classList.add('hidden');

            // Reset after 2 seconds
            setTimeout(() => {
                if (btnText) btnText.textContent = 'COMMIT & PUSH';
                if (btn) btn.disabled = false;
            }, 2000);

            // Show success message in chat with SHA and link
            const chatMessages = document.getElementById('chatMessages');
            if (chatMessages) {
                const msg = document.createElement('div');
                msg.className = 'chat-message ai';
                msg.style.color = 'var(--primary-color)';

                // Extract short SHA (first 7 chars)
                const shortSha = data.new_sha ? data.new_sha.substring(0, 7) : 'unknown';

                msg.innerHTML = `
                    ✓ COMMITTED TO BRANCH: ${branch}
                    <br><br>
                    <strong>Commit:</strong> <code style="background: var(--surface-color); padding: 0.2rem 0.5rem;">${shortSha}</code>
                    ${data.commit_url ? `<br><a href="${data.commit_url}" target="_blank" style="color: var(--secondary-color);">View on GitHub →</a>` : ''}
                `;

                chatMessages.appendChild(msg);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
        } else {
            alert("PUSH_FAILED: " + (data.error || data.detail || "UNKNOWN_ERROR"));
            // Reset button
            if (btn) btn.disabled = false;
            if (btnText) btnText.classList.remove('hidden');
            if (spinner) spinner.classList.add('hidden');
        }
    } catch (e) {
        console.error(e);
        alert("NETWORK_ERROR");
        // Reset button
        if (btn) btn.disabled = false;
        if (btnText) btnText.classList.remove('hidden');
        if (spinner) spinner.classList.add('hidden');
    }
};

// Save editor file
window.saveEditorFile = async function () {
    if (!monacoEditor || !monacoWorkingModel) {
        alert("EDITOR_NOT_READY.");
        return;
    }
    if (!currentRepo || !currentFilePath || !currentFileSha) {
        alert("NO_FILE_SELECTED.");
        return;
    }

    const code = monacoWorkingModel.getValue();
    const message = prompt("Enter commit message:", `Update ${currentFilePath}`);

    if (!message) return;

    // Get correct branch: PR branch > repo default > master
    const branch = currentPR
        ? (currentPR.head_branch || currentPR.base?.ref || 'master')
        : (currentRepo?.default_branch || 'master');

    try {
        const res = await fetch('/api/commit-file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                owner: currentRepo.owner,
                repo: currentRepo.name,
                path: currentFilePath,
                content: code,
                message: message,
                sha: currentFileSha,
                branch: branch,
                github_token: getToken()
            })
        });
        const data = await res.json();

        if (data.ok) {
            alert(`FILE_SAVED_TO_BRANCH: ${branch}`);
            // Update SHA to avoid conflict on next save
            currentFileSha = data.new_sha;
        } else {
            alert("SAVE_FAILED: " + (data.error || data.detail || "UNKNOWN_ERROR"));
        }
    } catch (e) {
        console.error(e);
        alert("NETWORK_ERROR");
    }
};

// Fetch Reports
window.fetchReports = async function () {
    const container = document.getElementById('reportsContainer');
    if (!container) return;

    container.innerHTML = '<div style="text-align: center; color: var(--text-dim); padding: 2rem;">LOADING_REPORTS...</div>';

    try {
        const res = await fetch('/api/reports');
        const data = await res.json();

        if (!data.reports || data.reports.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: var(--text-dim); padding: 2rem;">NO_REPORTS_AVAILABLE</div>';
            return;
        }

        container.innerHTML = data.reports.map((report, index) => `
        <div class="report-card" id="report-${index}">
            <div class="report-header" onclick="toggleReport(${index})">
                <div>
                    <div class="report-title">${report.title || 'ANALYSIS_REPORT'}</div>
                    <div class="report-meta">${report.timestamp || 'UNKNOWN_TIME'} | ${report.pr_number ? `PR #${report.pr_number}` : ''}</div>
                </div>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="report-body">
                ${report.summary ? `<div class="report-section"><h4>Summary</h4><p>${report.summary}</p></div>` : ''}
                
                ${report.metrics ? `
                    <div class="report-section">
                        <h4>Metrics</h4>
                        <div class="report-metrics">
                            ${Object.entries(report.metrics).map(([key, value]) => `
                                <div class="metric-card">
                                    <div class="metric-label">${key.replace(/_/g, ' ')}</div>
                                    <div class="metric-value">${value}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}
                
                ${report.issues && report.issues.length > 0 ? `
                    <div class="report-section">
                        <h4>Issues</h4>
                        <ul class="report-issues-list">
                            ${report.issues.map(issue => `
                                <li class="report-issue-item ${(issue.severity || '').toLowerCase()}">
                                    <strong>${issue.category || 'Issue'}:</strong> ${issue.message || ''}
                                    ${issue.file ? `<br><small style="color: var(--text-dim);">File: ${issue.file}</small>` : ''}
                                </li>
                            `).join('')}
                        </ul>
                    </div>
                ` : ''}
            </div>
        </div>
    `).join('');
    } catch (err) {
        console.error('Failed to fetch reports', err);
        container.innerHTML = '<div style="text-align: center; color: var(--danger-color); padding: 2rem;">FAILED_TO_LOAD_REPORTS</div>';
    }
};

window.toggleReport = function (index) {
    const reportCard = document.getElementById(`report-${index}`);
    if (reportCard) {
        reportCard.classList.toggle('expanded');
    }
}

// Manual Diff Analysis
window.analyzeManualDiff = async function () {
    const diff = document.getElementById('manualDiffInput').value;
    const resultDiv = document.getElementById('manualAnalysisResult');

    if (!diff) {
        alert("PLEASE_PASTE_DIFF_CONTENT");
        return;
    }

    resultDiv.innerHTML = '<div class="spinner-text">ANALYZING_DIFF...</div>';

    try {
        const res = await fetch('/api/analyze-manual-diff', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ diff })
        });
        const data = await res.json();

        if (data.analysis) {
            const summaryDiv = document.createElement('div');
            summaryDiv.innerHTML = `
                <div style="background: rgba(255,255,255,0.05); padding: 1rem; border-radius: 8px;">
                    <h3 style="color: var(--primary-color); margin-bottom: 0.5rem;">ANALYSIS_RESULT</h3>
                    <div style="white-space: pre-wrap;">${data.analysis}</div>
                </div>
            `;
            resultDiv.innerHTML = '';
            resultDiv.appendChild(summaryDiv);
        } else {
            resultDiv.innerHTML = '<div style="color: var(--danger-color);">ANALYSIS_FAILED</div>';
        }
    } catch (err) {
        resultDiv.innerHTML = '<div style="color: var(--danger-color);">NETWORK_ERROR</div>';
    }
};


// Fetch Repositories
window.fetchRepos = async function () {
    const grid = document.getElementById('reposGrid');
    if (!grid) return;

    grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim);">LOADING_REPOSITORIES...</div>';

    try {
        const res = await fetch('/api/repos', {
            headers: { 'github-token': getToken() }
        });

        if (res.status === 401) {
            window.location.href = '/login';
            return;
        }

        const repos = await res.json();

        if (!Array.isArray(repos) || repos.length === 0) {
            grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim);">NO_REPOSITORIES_FOUND.</div>';
            return;
        }

        grid.innerHTML = repos.map(repo => `
            <div class="card" onclick="window.location.href='/static/pr_list.html?owner=${repo.owner.login}&repo=${repo.name}'">
                <div class="card-title">
                    <span>${repo.name}</span>
                    ${repo.private ? '<span class="status-badge status-closed">PRIVATE</span>' : '<span class="status-badge status-open">PUBLIC</span>'}
                </div>
                <div class="card-meta">
                    OWNER: ${repo.owner.login} | STARS: ${repo.stargazers_count} | FORKS: ${repo.forks_count}
                </div>
                <div style="font-size: 0.9rem; color: var(--text-color); margin-top: 0.5rem;">
                    ${repo.description || 'NO_DESCRIPTION'}
                </div>
                <div style="margin-top: 0.5rem; font-size: 0.8rem; color: var(--text-dim);">
                    UPDATED: ${new Date(repo.updated_at).toLocaleDateString()}
                </div>
            </div>
        `).join('');

    } catch (err) {
        console.error('Failed to fetch repos', err);
        grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--danger-color);">SYSTEM_ERROR: FAILED_TO_FETCH_REPOSITORIES</div>';
    }
};

// Fetch PRs for a Repo
window.fetchRepoPRs = async function (owner, repo) {
    const grid = document.getElementById('prListGrid');
    const title = document.getElementById('repoTitle');

    if (title) title.textContent = `${owner}/${repo}`;
    if (!grid) return;

    grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim);">LOADING_PRS...</div>';

    try {
        const res = await fetch(`/api/repos/${owner}/${repo}/prs`, {
            headers: { 'Github-Token': getToken() }
        });

        if (res.status === 401) {
            window.location.href = '/login';
            return;
        }

        const prs = await res.json();

        if (!Array.isArray(prs) || prs.length === 0) {
            grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim);">NO PULL REQUESTS FOUND IN THIS REPOSITORY</div>';
            return;
        }

        grid.innerHTML = prs.map(pr => `
            <div class="card" onclick="window.location.href='/static/pr_details.html?owner=${owner}&repo=${repo}&pr=${pr.number}'">
                <div class="card-title">
                    <span>#${pr.number} ${pr.title}</span>
                    <span class="status-badge status-${pr.state === 'open' ? 'open' : 'closed'}">${pr.state}</span>
                </div>
                <div class="card-meta">
                    AUTHOR: ${pr.user.login} | CREATED: ${new Date(pr.created_at).toLocaleDateString()}
                </div>
                <div style="font-size: 0.9rem; color: var(--text-color); margin-top: 0.5rem; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">
                    ${pr.body || 'NO_DESCRIPTION'}
                </div>
            </div>
        `).join('');

    } catch (err) {
        console.error('Failed to fetch PRs', err);
        grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--danger-color);">SYSTEM_ERROR: FAILED_TO_FETCH_PRS</div>';
    }
};

// Global variable to cache analysis results
let cachedAnalysis = null;

// Fetch PR Details
window.fetchPRDetails = async function (owner, repo, prNumber) {
    const title = document.getElementById('prDetailTitle');
    const fileList = document.getElementById('fileListContainer');

    // New IDE layout elements
    const prRepoInfo = document.getElementById('prRepoInfo');
    const prTitle = document.getElementById('prTitle');

    // Show terminal loader for analysis
    showTerminalLoader();

    // Update IDE header immediately if present
    if (prRepoInfo) {
        prRepoInfo.textContent = `${owner}/${repo} // PR #${prNumber}`;
    }
    if (prTitle) {
        prTitle.textContent = 'LOADING...';
    }

    if (title) title.textContent = `LOADING #${prNumber}...`;
    if (fileList) fileList.innerHTML = '<div style="padding: 1rem; color: var(--text-dim);">LOADING_FILES...</div>';

    try {
        const res = await fetch(`/api/repos/${owner}/${repo}/prs/${prNumber}`, {
            headers: { 'Github-Token': getToken() }
        });

        if (res.status === 401) {
            window.location.href = '/login';
            return;
        }

        const data = await res.json();

        // Update Global State
        currentPR = data.pr;
        currentRepo = { owner: owner, name: repo }; // Simplified repo object

        // Update IDE layout header
        if (prTitle && data.pr) {
            prTitle.textContent = data.pr.title;
        }
        if (prRepoInfo && data.pr) {
            prRepoInfo.textContent = `${owner}/${repo} // ${data.pr.head.ref} // PR #${prNumber}`;
        }

        // Update Title
        if (title) {
            title.innerHTML = `
                <span style="color: var(--primary-color);">${owner}/${repo} #${prNumber}</span>
                <span style="color: var(--text-color); font-weight: normal;">${data.pr.title}</span>
                <span class="status-badge status-${data.pr.state === 'open' ? 'open' : 'closed'}">${data.pr.state}</span>
            `;
        }

        // Render Files
        if (fileList) {
            if (!data.files || data.files.length === 0) {
                fileList.innerHTML = '<div style="padding: 1rem; color: var(--text-dim);">NO_FILES_CHANGED.</div>';
            } else {
                fileList.innerHTML = data.files.map(file => `
                    <div class="file-item" onclick="window.openEditor('${file.raw_url}', '${file.filename}', '${file.sha}')">
                        <span>${file.filename}</span>
                        <span style="color: ${file.status === 'added' ? 'var(--primary-color)' : file.status === 'removed' ? 'var(--danger-color)' : 'var(--warning-color)'}; font-size: 0.7rem; text-transform: uppercase;">${file.status}</span>
                    </div>
                `).join('');
            }
        }

        // Cache the analysis for later display (don't show yet)
        cachedAnalysis = data.analysis;

        // Analysis is cached, will be displayed when user clicks "SHOW ANALYSIS" button
        // Show success in terminal and hide loader
        updateTerminalSuccess();

    } catch (err) {
        console.error('Failed to fetch PR details', err);
        if (title) title.textContent = 'ERROR_LOADING_PR';
        if (prTitle) prTitle.textContent = 'ERROR LOADING PR';
        if (fileList) fileList.innerHTML = '<div style="padding: 1rem; color: var(--danger-color);">FAILED_TO_LOAD_FILES</div>';
        hideTerminalLoader();
    }
};

// Terminal Loader Functions
function showTerminalLoader() {
    const loader = document.getElementById('terminalLoader');
    const body = document.getElementById('terminalBody');
    if (!loader || !body) return;

    body.innerHTML = '';

    const messages = [
        { text: '$ Initializing AI Code Review System...', type: 'info' },
        { text: '[INFO] Loading PR files and metadata', type: 'info' },
        { text: '>> Starting Multi-Agent Analysis Pipeline', type: '' },
        { text: '[AGENT-1] Security Analyzer: Running...', type: 'info' },
        { text: '[AGENT-2] Performance Analyzer: Running...', type: 'info' },
        { text: '[AGENT-3] Code Quality Checker: Running...', type: 'info' },
        { text: '[LINTER] Running static analysis...', type: 'warning' },
        { text: '[SYNTHESIS] Aggregating findings...', type: 'info' },
        { text: ' Waiting for analysis to complete...', type: '', hasCursor: true }
    ];

    let messageIndex = 0;

    function typeNextMessage() {
        if (messageIndex >= messages.length) return;

        const msg = messages[messageIndex];
        const line = document.createElement('div');
        line.className = `terminal-line ${msg.type}`;
        body.appendChild(line);

        let charIndex = 0;
        const typingSpeed = 30;

        function typeChar() {
            if (charIndex < msg.text.length) {
                line.textContent += msg.text[charIndex];
                charIndex++;
                body.scrollTop = body.scrollHeight;
                setTimeout(typeChar, typingSpeed);
            } else {
                if (msg.hasCursor) {
                    const cursor = document.createElement('span');
                    cursor.className = 'terminal-cursor';
                    line.appendChild(cursor);
                }
                messageIndex++;
                setTimeout(typeNextMessage, 200);
            }
        }

        typeChar();
    }

    typeNextMessage();

    loader.classList.add('active');
}

function hideTerminalLoader() {
    const loader = document.getElementById('terminalLoader');
    if (loader) loader.classList.remove('active');
}

function updateTerminalSuccess() {
    const body = document.getElementById('terminalBody');
    if (!body) return;

    const successMessages = [
        { text: '[SUCCESS] Multi-agent analysis completed', type: 'success' },
        { text: '$ All agents finished successfully', type: 'success' },
        { text: '$ Loading results...', type: 'info' }
    ];

    let msgIndex = 0;

    function typeSuccessMessage() {
        if (msgIndex >= successMessages.length) {
            // All messages typed, hide after delay
            setTimeout(() => hideTerminalLoader(), 1200);
            return;
        }

        const msg = successMessages[msgIndex];
        const line = document.createElement('div');
        line.className = `terminal-line ${msg.type}`;
        body.appendChild(line);

        let charIndex = 0;

        function typeChar() {
            if (charIndex < msg.text.length) {
                line.textContent += msg.text[charIndex];
                charIndex++;
                body.scrollTop = body.scrollHeight;
                setTimeout(typeChar, 25);
            } else {
                msgIndex++;
                setTimeout(typeSuccessMessage, 150);
            }
        }

        typeChar();
    }

    typeSuccessMessage();
}

// Initialization Logic (Router)
document.addEventListener('DOMContentLoaded', () => {
    // Sidebar Toggle Logic
    const sidebar = document.getElementById('sidebar');
    const dashboardContainer = document.querySelector('.dashboard-container');
    const sidebarToggle = document.getElementById('sidebarToggle');

    if (sidebar && dashboardContainer && sidebarToggle) {
        // Don't auto-collapse on dashboard load - always start expanded
        // User can manually toggle if needed

        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            dashboardContainer.classList.toggle('sidebar-collapsed');
            localStorage.setItem('sidebar_collapsed', sidebar.classList.contains('collapsed'));
        });
    }

    // Shared Logic: Check Login
    if (document.querySelector('.dashboard-container')) {
        // Declare user variable outside conditional block so it's accessible throughout
        const user = JSON.parse(localStorage.getItem('gh_user') || '{}');

        // specific check: if we are processing a login hash, DO NOT redirect
        if (window.location.hash && window.location.hash.includes('token=')) {
            console.log('Processing OAuth callback, skipping auth check redirect...');
            // let the hash handler (defined above) do its work
        } else {
            if (!user.login) {
                window.location.href = '/login';
                return;
            }
        }

        // Ensure sidebar is visible by default (remove hidden classes)
        if (sidebar && dashboardContainer) {
            sidebar.classList.remove('hidden');
            dashboardContainer.classList.remove('sidebar-hidden');
        }

        // Set User Info
        const avatarEl = document.getElementById('userAvatar');
        const nameEl = document.getElementById('userName');
        const loginEl = document.getElementById('userLogin');

        if (avatarEl) avatarEl.src = user.avatar_url;
        if (nameEl) nameEl.textContent = user.name || user.login;
        if (loginEl) loginEl.textContent = `@${user.login}`;

        // Logout
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => {
                localStorage.removeItem('gh_token');
                localStorage.removeItem('gh_user');
                window.location.href = '/login';
            });
        }
    }

    // Route Detection
    const path = window.location.pathname;
    const params = new URLSearchParams(window.location.search);

    if (path.includes('dashboard')) {
        fetchActivityLogs();
        // Removed auto-refresh to prevent constant loading
        // User can manually click REFRESH button when needed
    }
    else if (path.includes('repositories.html')) {
        fetchRepos();
    }
    else if (path.includes('pr_list.html')) {
        const owner = params.get('owner');
        const repo = params.get('repo');
        if (owner && repo) {
            fetchRepoPRs(owner, repo);
        } else {
            alert("MISSING_REPO_PARAMETERS");
            window.location.href = '/static/repositories.html';
        }
    }
    else if (path.includes('pr_details.html')) {
        const owner = params.get('owner');
        const repo = params.get('repo');
        const pr = params.get('pr');

        if (owner && repo && pr) {
            fetchPRDetails(owner, repo, pr);
        } else {
            alert("MISSING_PR_PARAMETERS");
            window.location.href = '/static/repositories.html';
        }
    }
    else if (path.includes('editor.html')) {
        const owner = params.get('owner');
        const repo = params.get('repo');
        const pr = params.get('pr'); // Optional, but good for context
        const filename = params.get('filename');
        const sha = params.get('sha');

        if (owner && repo && filename) {
            // Set global state
            currentRepo = { owner, name: repo };
            if (pr) currentPR = { number: pr, head_branch: 'main' }; // We might need to fetch full PR details if branch is needed

            // Wait for Monaco to load then open file
            const checkMonaco = setInterval(() => {
                if (window.monacoEditor && window.monacoWorkingModel) {
                    clearInterval(checkMonaco);
                    openEditor(null, filename, sha); // URL is null because we use backend fetch
                }
            }, 100);
        } else {
            alert("MISSING_EDITOR_PARAMETERS");
            window.location.href = '/dashboard';
        }
    }
    else if (path.includes('reports.html')) {
        fetchReports();
    }
});

const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar = document.getElementById('sidebar');
if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener("click", () => {
        sidebar.classList.toggle("collapsed");
        const dashboardContainer = document.querySelector('.dashboard-container');
        if (dashboardContainer) dashboardContainer.classList.toggle('sidebar-collapsed');
    });
}

// Tab Switching
window.switchTab = function (tabName) {
    // Update Tab Buttons
    document.querySelectorAll('.pr-tab').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('onclick') && btn.getAttribute('onclick').includes(tabName)) {
            btn.classList.add('active');
        }
    });

    // Update Tab Content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    const activeContent = document.getElementById(`tab-${tabName}`);
    if (activeContent) {
        activeContent.classList.add('active');
    }
};

// Chat Placeholder
// Chat with Backend (Enhanced with Code Modification Support)
window.sendChatMessage = async function () {
    const input = document.getElementById('chatInput');
    const messages = document.getElementById('chatMessages');
    if (!input || !messages) return;

    const text = input.value.trim();
    if (!text) return;

    // User Message
    const userMsg = document.createElement('div');
    userMsg.className = 'chat-message user';
    userMsg.textContent = text;
    messages.appendChild(userMsg);

    input.value = '';
    messages.scrollTop = messages.scrollHeight;

    // AI Loading Message
    const aiMsg = document.createElement('div');
    aiMsg.className = 'chat-message ai';
    aiMsg.innerHTML = '<span class="typing-indicator">●●●</span>';
    messages.appendChild(aiMsg);
    messages.scrollTop = messages.scrollHeight;

    try {
        // Prepare context with current file information
        const code = monacoWorkingModel ? monacoWorkingModel.getValue() : '';

        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                context: {
                    current_file: {
                        filename: currentFilePath || 'unknown',
                        content: code
                    },
                    analysis: currentAnalysis,
                    issues: window.currentEditorIssues || []
                },
                history: chatHistory
            })
        });

        const data = await res.json();

        // Update History
        chatHistory.push({ role: 'user', content: text });
        chatHistory.push({ role: 'assistant', content: data.response });

        // Check if push/commit was requested
        if (data.push_requested) {
            // Show AI response first
            aiMsg.innerHTML = `
                <div style="border-left: 3px solid var(--secondary-color); padding-left: 0.5rem;">
                    <div style="white-space: pre-wrap;">${data.response}</div>
                </div>
            `;
            messages.scrollTop = messages.scrollHeight;

            // Execute the push
            await executePushToBranch(data.commit_message || 'AI-assisted changes');
        }
        // Check if code was modified
        else if (data.code_modified && data.modified_code) {
            // Update Monaco editor with modified code
            if (monacoWorkingModel) {
                monacoWorkingModel.setValue(data.modified_code);
            }

            // Show special response for code modifications
            aiMsg.innerHTML = `
                <div style="border-left: 3px solid var(--success-color); padding-left: 0.5rem;">
                    <div style="color: var(--success-color); font-weight: bold; margin-bottom: 0.5rem;">
                        CODE MODIFIED
                    </div>
                    <div style="white-space: pre-wrap;">${data.response}</div>
                    <div style="margin-top: 0.5rem; padding: 0.5rem; background: rgba(0,255,0,0.1); border-radius: 4px; font-size: 0.85rem;">
                        Changes applied to editor
                    </div>
                </div>
            `;
        } else {
            // Regular chat response - use marked if available, otherwise plain text
            if (typeof marked !== 'undefined') {
                aiMsg.innerHTML = marked.parse(data.response);
            } else {
                aiMsg.innerHTML = `<div style="white-space: pre-wrap;">${data.response}</div>`;
            }
        }

    } catch (err) {
        console.error('Chat error:', err);
        aiMsg.innerHTML = `<span style="color: var(--danger-color);">ERROR: ${err.message || 'FAILED_TO_SEND_MESSAGE'}</span>`;
    }

    messages.scrollTop = messages.scrollHeight;
};

// File rendering has been updated in fetchPRDetails (line 881-888)

// PR Details Tab Switching
window.switchPRTab = function (tabName) {
    // Switch tab buttons
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        if (btn.textContent.trim().toLowerCase() === tabName.toLowerCase()) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // Switch tab content
    const tabContents = document.querySelectorAll('.tab-content');
    tabContents.forEach(content => {
        if (content.id === `tab-${tabName}`) {
            content.classList.add('active');
        } else {
            content.classList.remove('active');
        }
    });

    // Trigger Monaco resize if switching to files tab
    if (tabName === 'files' && monacoEditor) {
        setTimeout(() => monacoEditor.layout(), 100);
    }
};

// Display cached analysis results without re-running analysis
window.displayCachedAnalysis = function () {
    if (!cachedAnalysis) {
        alert("NO ANALYSIS DATA AVAILABLE. PLEASE RELOAD THE PR.");
        return;
    }

    const analysis = cachedAnalysis;

    // Helper to render issues
    const renderIssues = (issues, emptyMsg) => {
        if (!issues || issues.length === 0) return `<p style="color: var(--text-dim);">${emptyMsg}</p>`;

        return issues.map(issue => `
            <div style="margin-bottom: 0.75rem; padding: 0.5rem; border-left: 2px solid var(--secondary-color); background: var(--surface-color);">
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: var(--secondary-color); font-weight: bold;">${issue.category || 'ISSUE'}</span>
                    <span style="color: var(--text-dim); font-size: 0.8rem;">${issue.severity || 'INFO'}</span>
                </div>
                <div style="color: var(--text-color); margin-top: 0.25rem;">${issue.message || ''}</div>
                ${issue.file ? `<div style="color: var(--text-dim); font-size: 0.8rem; margin-top: 0.25rem;">File: ${issue.file} ${issue.line ? `(Line ${issue.line})` : ''}</div>` : ''}
                ${issue.suggestion ? `<div style="color: var(--text-dim); font-size: 0.8rem; margin-top: 0.25rem; border-top: 1px dashed var(--surface-border); padding-top: 0.25rem;">💡 ${issue.suggestion}</div>` : ''}
            </div>
        `).join('');
    };

    // Update main report content (summary)
    const reportContent = document.getElementById('reportContent');
    if (reportContent) {
        reportContent.innerHTML = `
            <div style="color: var(--primary-color); margin-bottom: 1rem;">
                <strong>ANALYSIS COMPLETE</strong>
            </div>
            <div style="color: var(--text-color); line-height: 1.6;">
                ${analysis.summary || 'Analysis completed successfully.'}
            </div>
            <div style="margin-top: 1rem; padding: 0.75rem; background: rgba(0,255,0,0.1); border-radius: 4px;">
                <strong style="color: var(--success-color);">RECOMMENDATION:</strong> ${analysis.recommendation || 'Review'}
            </div>
        `;
    }

    // Update linter results
    const linterResults = document.getElementById('linterResults');
    if (linterResults) {
        linterResults.innerHTML = renderIssues(analysis.linter, 'No linter issues found.');
    }

    // Update code quality results
    const codeQualityResults = document.getElementById('codeQualityResults');
    if (codeQualityResults) {
        // Use warning color for code quality
        const issuesHtml = (analysis.issues || []).map(issue => `
            <div style="margin-bottom: 0.75rem; padding: 0.5rem; border-left: 2px solid var(--warning-color); background: var(--surface-color);">
                <div style="color: var(--warning-color); font-weight: bold;">${issue.category || 'ISSUE'}</div>
                <div style="color: var(--text-color); margin-top: 0.25rem;">${issue.message || ''}</div>
                ${issue.file ? `<div style="color: var(--text-dim); font-size: 0.8rem; margin-top: 0.25rem;">File: ${issue.file} ${issue.line ? `(Line ${issue.line})` : ''}</div>` : ''}
                ${issue.suggestion ? `<div style="color: var(--text-dim); font-size: 0.8rem; margin-top: 0.25rem; border-top: 1px dashed var(--surface-border); padding-top: 0.25rem;">💡 ${issue.suggestion}</div>` : ''}
            </div>
        `).join('');
        codeQualityResults.innerHTML = issuesHtml || '<p style="color: var(--text-dim);">No code quality issues found.</p>';
    }

    // Update security results
    const securityResults = document.getElementById('securityResults');
    if (securityResults) {
        securityResults.innerHTML = renderIssues(analysis.security, 'No security vulnerabilities found.');
    }

    // Update performance results
    const performanceResults = document.getElementById('performanceResults');
    if (performanceResults) {
        performanceResults.innerHTML = renderIssues(analysis.performance, 'No performance issues found.');
    }
};

// Run Multi-Agent Analysis
window.runMultiAgentAnalysis = async function () {
    if (!currentRepo || !currentPR) {
        alert("NO PR SELECTED. PLEASE SELECT A PR FIRST.");
        return;
    }

    const analysisBtn = document.getElementById('analysisBtnText');
    const analysisSpinner = document.getElementById('analysisSpinner');
    const reportContent = document.getElementById('reportContent');
    const linterResults = document.getElementById('linterResults');
    const codeQualityResults = document.getElementById('codeQualityResults');
    const securityResults = document.getElementById('securityResults');
    const performanceResults = document.getElementById('performanceResults');

    // Show loading state
    if (analysisBtn) analysisBtn.classList.add('hidden');
    if (analysisSpinner) analysisSpinner.classList.remove('hidden');

    if (reportContent) {
        reportContent.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 2rem;">RUNNING MULTI-AGENT ANALYSIS...</div>';
    }

    try {
        const res = await fetch(`/api/repos/${currentRepo.owner}/${currentRepo.name}/prs/${currentPR.number}/analyze`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                github_token: getToken()
            })
        });

        const data = await res.json();

        if (data.ok && data.analysis) {
            const analysis = data.analysis;

            // Update main report content
            if (reportContent) {
                reportContent.innerHTML = `
                    <div style="color: var(--primary-color); margin-bottom: 1rem;">
                        <strong>ANALYSIS COMPLETE</strong>
                    </div>
                    <div style="color: var(--text-color); line-height: 1.6;">
                        ${analysis.summary || 'Analysis completed successfully.'}
                    </div>
                `;
            }

            // Helper to render issues
            const renderIssues = (issues, emptyMsg) => {
                if (!issues || issues.length === 0) return `<p style="color: var(--text-dim);">${emptyMsg}</p>`;

                return issues.map(issue => `
                    <div style="margin-bottom: 0.75rem; padding: 0.5rem; border-left: 2px solid var(--secondary-color); background: var(--surface-color);">
                        <div style="display: flex; justify-content: space-between;">
                            <span style="color: var(--secondary-color); font-weight: bold;">${issue.category || 'ISSUE'}</span>
                            <span style="color: var(--text-dim); font-size: 0.8rem;">${issue.severity || 'INFO'}</span>
                        </div>
                        <div style="color: var(--text-color); margin-top: 0.25rem;">${issue.message || ''}</div>
                        ${issue.file ? `<div style="color: var(--text-dim); font-size: 0.8rem; margin-top: 0.25rem;">File: ${issue.file} ${issue.line ? `(Line ${issue.line})` : ''}</div>` : ''}
                        ${issue.suggestion ? `<div style="color: var(--text-dim); font-size: 0.8rem; margin-top: 0.25rem; border-top: 1px dashed var(--surface-border); padding-top: 0.25rem;">💡 ${issue.suggestion}</div>` : ''}
                    </div>
                `).join('');
            };

            // Update linter results
            if (linterResults) {
                linterResults.innerHTML = renderIssues(analysis.linter, 'No linter issues found.');
            }

            // Update code quality results
            if (codeQualityResults) {
                // Use warning color for code quality
                const issuesHtml = (analysis.issues || []).map(issue => `
                    <div style="margin-bottom: 0.75rem; padding: 0.5rem; border-left: 2px solid var(--warning-color); background: var(--surface-color);">
                        <div style="color: var(--warning-color); font-weight: bold;">${issue.category || 'ISSUE'}</div>
                        <div style="color: var(--text-color); margin-top: 0.25rem;">${issue.message || ''}</div>
                         ${issue.file ? `<div style="color: var(--text-dim); font-size: 0.8rem; margin-top: 0.25rem;">File: ${issue.file} ${issue.line ? `(Line ${issue.line})` : ''}</div>` : ''}
                    </div>
                `).join('');
                codeQualityResults.innerHTML = issuesHtml || '<p style="color: var(--text-dim);">No code quality issues found.</p>';
            }

            // Update security results
            if (securityResults) {
                securityResults.innerHTML = renderIssues(analysis.security, 'No security vulnerabilities found.');
            }

            // Update performance results
            if (performanceResults) {
                performanceResults.innerHTML = renderIssues(analysis.performance, 'No performance issues found.');
            }
        } else {
            if (reportContent) {
                reportContent.innerHTML = `
                    <div style="color: var(--danger-color); text-align: center; padding: 2rem;">
                        ANALYSIS FAILED: ${data.error || data.detail || 'UNKNOWN ERROR'}
                    </div>
                `;
            }
        }
    } catch (error) {
        console.error('Analysis error:', error);
        if (reportContent) {
            reportContent.innerHTML = `
                <div style="color: var(--danger-color); text-align: center; padding: 2rem;">
                    NETWORK ERROR: Failed to run analysis
                </div>
            `;
        }
    } finally {
        // Reset button state
        if (analysisBtn) analysisBtn.classList.remove('hidden');
        if (analysisSpinner) analysisSpinner.classList.add('hidden');
    }
};

// =========================================
// IDE Layout Functions
// =========================================

function toggleChatPanel() {
    const panel = document.getElementById('chatPanel');
    if (panel) {
        panel.classList.toggle('visible');
    }
}

function switchIDEView(viewName) {
    const icon = document.getElementById(`tab-icon-${viewName}`);
    const sidebar = document.getElementById('ideSidebar');
    const filesView = document.getElementById('view-files');
    const reportView = document.getElementById('view-report');

    // VS Code behavior: clicking active icon toggles sidebar
    if (icon && icon.classList.contains('active') && viewName === 'files') {
        // Toggle sidebar visibility
        if (sidebar) {
            sidebar.classList.toggle('collapsed');
            // Resize editor after transition
            setTimeout(() => {
                if (window.monacoEditor && typeof window.monacoEditor.layout === 'function') {
                    window.monacoEditor.layout();
                }
            }, 200);
        }
        return;
    }

    // Update activity bar icons
    document.querySelectorAll('.activity-icon').forEach(el => el.classList.remove('active'));
    if (icon) icon.classList.add('active');

    // Show/hide views
    if (viewName === 'files') {
        if (filesView) filesView.style.display = 'flex';
        if (reportView) reportView.classList.remove('active');
        // Ensure sidebar is visible when switching to files view
        if (sidebar) sidebar.classList.remove('collapsed');
    } else if (viewName === 'report') {
        if (filesView) filesView.style.display = 'none';
        if (reportView) reportView.classList.add('active');
        // Hide sidebar when viewing report
        if (sidebar) sidebar.classList.add('collapsed');
    }

    // Resize editor if visible
    if (viewName === 'files' && window.monacoEditor && typeof window.monacoEditor.layout === 'function') {
        setTimeout(() => window.monacoEditor.layout(), 50);
    }
}

function toggleSidebar() {
    const sidebar = document.getElementById('ideSidebar');
    if (sidebar) {
        sidebar.classList.toggle('collapsed');
        // Resize editor after transition
        setTimeout(() => {
            if (window.monacoEditor && typeof window.monacoEditor.layout === 'function') {
                window.monacoEditor.layout();
            }
        }, 200);
    }
}

// Resizable Sidebar
let isResizing = false;
let sidebarWidth = 250;

function initSidebarResize() {
    const sidebar = document.getElementById('ideSidebar');
    if (!sidebar) return;

    // Create resize handle
    const resizeHandle = document.createElement('div');
    resizeHandle.className = 'sidebar-resize-handle';
    sidebar.appendChild(resizeHandle);

    resizeHandle.addEventListener('mousedown', function (e) {
        isResizing = true;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', function (e) {
        if (!isResizing) return;

        const newWidth = e.clientX - 50; // 50px for activity bar
        if (newWidth >= 150 && newWidth <= 600) {
            sidebar.style.width = newWidth + 'px';
            sidebarWidth = newWidth;
        }
    });

    document.addEventListener('mouseup', function () {
        if (isResizing) {
            isResizing = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            // Resize editor
            if (window.monacoEditor && typeof window.monacoEditor.layout === 'function') {
                window.monacoEditor.layout();
            }
        }
    });
}

// Initialize resize on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSidebarResize);
} else {
    initSidebarResize();
}
