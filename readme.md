# AI Code Reviewer & PR Agent 🤖

An intelligent, automated code review system powered by Google Gemini. This agent integrates with GitHub Webhooks to analyze Pull Requests in real-time, providing actionable feedback on code quality, security, performance, and style. It also features a dashboard for manual review and an interactive chat for discussing code improvements.

## 🚀 Features

- **Multi-Agent Analysis**:
  - **Linter Agent**: Checks for syntax errors and style violations.
  - **Security Agent**: Identifies potential vulnerabilities (e.g., injection flaws, hardcoded secrets).
  - **Performance Agent**: Suggests optimizations for speed and efficiency.
  - **Code Quality Agent**: Reviews readability, maintainability, and best practices.
- **Automated PR Reviews**: Automatically analyzes new PRs and posts comments/reports.
- **Interactive Dashboard**: View analysis history, recent commits, and file changes.
- **Chat with Codebase**: Ask questions about the code and get context-aware answers.
- **Auto-Fix**: AI-generated code fixes that can be applied directly to the branch.
- **Render Ready**: Pre-configured for easy deployment on Render.com.

## 🛠️ Tech Stack

- **Backend**: Python, FastAPI
- **AI Model**: Google Gemini 1.5 Flash
- **Frontend**: HTML5, CSS3 (Terminal/Hacker Theme), JavaScript
- **Deployment**: Render (Gunicorn + Uvicorn)

## 📋 Prerequisites

- Python 3.11+
- A GitHub Account & Personal Access Token (PAT)
- Google Gemini API Key

## ⚙️ Local Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/codereviewer.git
   cd codereviewer
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Mac/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**
   Create a `.env` file in the root directory:
   ```env
   # GitHub Configuration
   GITHUB_TOKEN=your_github_pat_here
   GITHUB_WEBHOOK_SECRET=your_webhook_secret_here
   GITHUB_CLIENT_ID=your_oauth_client_id
   GITHUB_CLIENT_SECRET=your_oauth_client_secret

   # Google Gemini Configuration
   GOOGLE_API_KEY=your_gemini_api_key_here
   ```

5. **Run the Application**
   ```bash
   uvicorn app.main:app --reload
   ```
   Access the dashboard at `http://localhost:8000`.

## ☁️ Deployment (Render)

This project is configured for easy deployment on Render.

1. **Push to GitHub**: Ensure your code is pushed to a GitHub repository.
2. **Create Web Service**:
   - Go to [Render Dashboard](https://dashboard.render.com/).
   - Select **New +** > **Web Service**.
   - Connect your repository.
3. **Configuration**:
   - Render will automatically detect `render.yaml`.
   - **Important**: You must manually add your environment variables (`GITHUB_TOKEN`, `GOOGLE_API_KEY`, etc.) in the Render dashboard during setup.
4. **Deploy**: Click create. Your app will be live in minutes!

> **Note**: On Render's free tier, the filesystem is ephemeral. Data stored in `data/` (like analysis logs) will be lost on restart. For production persistence, consider integrating a database.

## 🔌 Webhook Setup

To enable automatic PR reviews:
1. Go to your GitHub Repository Settings > **Webhooks**.
2. Click **Add webhook**.
3. **Payload URL**: `https://your-app-url.onrender.com/webhook`
4. **Content type**: `application/json`
5. **Secret**: The same value as `GITHUB_WEBHOOK_SECRET` in your env.
6. **Events**: Select "Let me select individual events" and check **Pull requests**.

## 🛡️ License

MIT License