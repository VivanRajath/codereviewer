document.getElementById('analyzeForm').addEventListener('submit', async function (e) {
    e.preventDefault();

    const submitBtn = document.getElementById('submitBtn');
    const loadingDiv = document.getElementById('loading');
    const errorDiv = document.getElementById('error');
    const resultsDiv = document.getElementById('results');
    const jsonOutput = document.getElementById('jsonOutput');

    // Reset UI
    submitBtn.disabled = true;
    loadingDiv.classList.remove('hidden');
    errorDiv.classList.add('hidden');
    resultsDiv.classList.add('hidden');
    jsonOutput.textContent = '';

    const formData = new FormData(e.target);
    const data = {
        owner: formData.get('owner'),
        repo: formData.get('repo'),
        pr_number: parseInt(formData.get('pr_number')),
        github_token: formData.get('github_token') || null
    };

    try {
        const response = await fetch('/analyze-pr', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok && result.ok) {
            jsonOutput.textContent = JSON.stringify(result.analysis, null, 2);
            resultsDiv.classList.remove('hidden');
        } else {
            const errorMsg = result.error || result.detail || 'An unknown error occurred';
            errorDiv.textContent = `Error: ${errorMsg}`;
            errorDiv.classList.remove('hidden');
        }
    } catch (error) {
        errorDiv.textContent = `Network Error: ${error.message}`;
        errorDiv.classList.remove('hidden');
    } finally {
        submitBtn.disabled = false;
        loadingDiv.classList.add('hidden');
    }
});
