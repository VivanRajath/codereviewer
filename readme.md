# AI Code Reviewer & PR Agent

> **Lyzer AI Backend Intern Challenge Submission**

An intelligent automated code review system powered by Google Gemini that integrates with GitHub to provide real-time pull request analysis, security scanning, and actionable feedback.

## ✨ Overview

This project delivers comprehensive code analysis through multiple specialized agents, combining automated PR reviews with an interactive dashboard for manual code inspection. Built for the Lyzer AI Backend Intern Challenge, it extends beyond basic requirements to include chatbot capabilities, individual file reviews, and automated code improvement suggestions.

## 🎯 Key Features

### Automated Analysis
- **Multi-Agent Architecture**: Four specialized agents work in parallel
  - **Linter Agent**: Detects syntax errors and style violations
  - **Security Agent**: Identifies vulnerabilities including injection flaws and exposed secrets
  - **Performance Agent**: Recommends optimizations for speed and resource efficiency
  - **Code Quality Agent**: Evaluates readability, maintainability, and adherence to best practices

### GitHub Integration
- **Webhook-Triggered Reviews**: Automatically analyzes pull requests as they're created
- **Inline Comments**: Posts detailed feedback directly on PR diffs
- **Auto-Fix Suggestions**: Generates code improvements that can be committed to the branch

### Interactive Interface
- **Dashboard**: Visualize analysis history, recent commits, and file-level changes
- **Codebase Chat**: Ask questions about the code and receive context-aware answers
- **Manual Review Tools**: Trigger analysis for specific files or commits on demand

## 🏗️ Architecture

**Backend**: FastAPI (Python)  
**AI Engine**: Google Gemini 1.5 Flash  
**Frontend**: HTML5/CSS3/JavaScript (Terminal-inspired UI)  
**Deployment**: Render (Gunicorn + Uvicorn workers)

## 🚦 Getting Started

### Prerequisites

- Python 3.11 or higher
- GitHub Personal Access Token with repo permissions
- Google Gemini API key

### Installation


```bash
# Clone the repository
git clone https://github.com/yourusername/codereviewer.git
cd codereviewer

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```


### Configuration

Create a `.env` file in the project root:

```env
# GitHub
GITHUB_TOKEN=ghp_your_token_here
GITHUB_WEBHOOK_SECRET=your_webhook_secret
GITHUB_CLIENT_ID=your_oauth_client_id
GITHUB_CLIENT_SECRET=your_oauth_client_secret

# Google Gemini
GOOGLE_API_KEY=your_gemini_api_key
```

### Running Locally

```bash
uvicorn app.main:app --reload
```

Navigate to `http://localhost:8000` to access the dashboard.

## 🌐 Live Demo

**Deployment**: https://codereviewer-0nfb.onrender.com/

The application is hosted on Render with production-ready configuration using Gunicorn and Uvicorn workers.

## 📁 Project Structure

```
codereviewer/
├── app/
│   ├── main.py           # FastAPI application entry point
│   ├── agents/           # Multi-agent analysis logic
│   ├── routes/           # API endpoints
│   └── services/         # GitHub & Gemini integrations
├── static/               # Frontend assets
├── templates/            # HTML templates
├── requirements.txt      # Python dependencies
└── .env                  # Environment configuration
```

##  Security Notes

- Never commit `.env` files or expose API keys
- GitHub webhooks should use secret validation
- Use environment variables for all sensitive configuration

## 🤝 Contributing

This project was created as part of the Lyzer AI Backend Intern Challenge. Feedback and suggestions are welcome through issues or pull requests.

## 📄 License

MIT License - see LICENSE file for details

---

**Built with** ❤️ **for the Lyzer AI Backend Intern Challenge**
