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

    // Show loading state
    if (btn) btn.disabled = true;
    if (btnText) btnText.classList.add('hidden');
    if (spinner) spinner.classList.remove('hidden');

    const code = monacoWorkingModel.getValue();
    const message = prompt("ENTER_COMMIT_MESSAGE:", `Update ${currentFilePath}`);

    if (!message) {
        // Reset button state
        if (btn) btn.disabled = false;
        if (btnText) btnText.classList.remove('hidden');
        if (spinner) spinner.classList.add('hidden');
        return;
    }

    const branch = currentPR ? (currentPR.head.ref || currentPR.head_branch || 'main') : 'main';

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

            // Show success message in chat
            const chatMessages = document.getElementById('chatMessages');
            if (chatMessages) {
                const msg = document.createElement('div');
                msg.className = 'chat-message ai';
                msg.style.color = 'var(--primary-color)';
                msg.textContent = `✓ Committed to branch: ${branch}`;
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
