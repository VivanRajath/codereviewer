// Switch between PR tabs (FILES and REPORT)
window.switchPRTab = function (tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });

    const activeTab = document.getElementById(`tab-${tabName}`);
    if (activeTab) {
        activeTab.classList.add('active');
    }

    // If switching to report tab, load detailed analysis
    if (tabName === 'report' && currentRepo && currentPR) {
        loadDetailedReport(currentRepo.owner, currentRepo.name, currentPR.number);
    }
};

// Load detailed multi-agent report
async function loadDetailedReport(owner, repo, prNumber) {
    const analysisContainer = document.getElementById('reportAnalysisContainer');
    const linterContainer = document.getElementById('reportLinterResults');

    if (analysisContainer) {
        analysisContainer.innerHTML = '<div style="color: var(--primary-color);">ANALYZING...</div>';
    }

    try {
        const res = await fetch(`/api/repos/${owner}/${repo}/prs/${prNumber}`, {
            headers: { 'Github-Token': getToken() }
        });

        const data = await res.json();
        const analysis = data.analysis;

        // Display multi-agent analysis
        if (analysisContainer && analysis) {
            let html = `
                <div style="border: 1px solid var(--primary-color); padding: 1rem; margin-bottom: 1rem;">
                    <h3 style="color: var(--primary-color); margin-bottom: 0.5rem;">SUMMARY</h3>
                    <p>${analysis.summary || 'No summary available.'}</p>
                </div>
            `;

            if (analysis.issues && analysis.issues.length > 0) {
                html += '<h3 style="color: var(--secondary-color); margin-bottom: 0.5rem;">ISSUES FOUND (' + analysis.issues.length + ')</h3>';
                analysis.issues.forEach((issue, idx) => {
                    const severityClass = (issue.severity || 'info').toLowerCase();
                    html += `
                        <div class="issue-card ${severityClass}" 
                             style="cursor: pointer; margin-bottom: 0.5rem;"
                             onclick="highlightIssueInReport('${issue.file}', ${issue.line})">
                            <strong>${issue.category || 'Issue'}</strong> - ${issue.severity || 'INFO'}
                            <br>
                            <span style="color: var(--text-color);">${issue.message}</span>
                            <br>
                            <small style="color: var(--text-dim);">File: ${issue.file} | Line: ${issue.line || 'N/A'}</small>
                        </div>
                    `;
                });
            } else {
                html += '<div style="color: var(--primary-color); margin-top: 1rem;">✓ NO ISSUES FOUND</div>';
            }

            analysisContainer.innerHTML = html;
        }

        // Display linter results
        if (linterContainer) {
            if (analysis && analysis.issues) {
                const lintIssues = analysis.issues.filter(i => i.category === 'Linting' || i.category === 'Syntax');

                if (lintIssues.length > 0) {
                    let linterHtml = '<h3 style="color: var(--warning-color); margin-bottom: 0.5rem;">LINTING ERRORS (' + lintIssues.length + ')</h3>';
                    lintIssues.forEach(lint => {
                        linterHtml += `
                            <div style="border-left: 2px solid var(--warning-color); padding: 0.5rem; margin-bottom: 0.5rem; background: var(--surface-color);">
                                <strong>${lint.file}</strong>:${lint.line || '?'}
                                <br>
                                <span style="color: var(--text-color);">${lint.message}</span>
                            </div>
                        `;
                    });
                    linterContainer.innerHTML = linterHtml;
                } else {
                    linterContainer.innerHTML = '<div style="color: var(--primary-color);">✓ No linting errors</div>';
                }
            } else {
                linterContainer.innerHTML = '<div style="color: var(--text-dim);">No linter data available</div>';
            }
        }

    } catch (err) {
        console.error('Failed to load detailed report', err);
        if (analysisContainer) {
            analysisContainer.innerHTML = '<div style="color: var(--danger-color);">FAILED TO LOAD ANALYSIS</div>';
        }
    }
}

// Highlight issue in report editor (placeholder - would need Monaco setup)
window.highlightIssueInReport = function (file, line) {
    const filenameEl = document.getElementById('reportEditorFileName');
    if (filenameEl) {
        filenameEl.textContent = `${file}:${line}`;
    }
    // TODO: Load file content and highlight line in report Monaco editor
    alert(`Would jump to ${file}:${line}`);
};
