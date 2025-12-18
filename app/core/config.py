import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv(override=True)


class Settings:
    """Centralized application settings"""
    
    # GitHub
    GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN")
    GITHUB_WEBHOOK_SECRET: Optional[str] = os.getenv("GITHUB_WEBHOOK_SECRET")
    GITHUB_CLIENT_ID: Optional[str] = os.getenv("GITHUB_CLIENT_ID")
    GITHUB_CLIENT_SECRET: Optional[str] = os.getenv("GITHUB_CLIENT_SECRET")
    
    # API Keys
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")
    
    # Grok keys
    GROK_KEYS = [
        os.getenv("GROK_1"),
        os.getenv("GROK_2"),
        os.getenv("GROK_3"),
        os.getenv("GROK_4"),
        os.getenv("GROK_5"),
    ]
    GROK_KEYS = [k for k in GROK_KEYS if k]
    
    # Gemini keys
    GEMINI_KEYS = [
        os.getenv("GEMINI_API_KEY_1"),
        os.getenv("GEMINI_API_KEY_2"),
        os.getenv("GEMINI_API_KEY_3"),
        os.getenv("GEMINI_API_KEY_4"),
    ]
    GEMINI_KEYS = [k for k in GEMINI_KEYS if k]
    
    # App Settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default-secret-key-change-in-production")
    BASE_URL: Optional[str] = os.getenv("BASE_URL", "https://codereviewer-0nfb.onrender.com")
    
    # Validation
    @classmethod
    def validate_oauth(cls) -> bool:
        """Check if OAuth credentials are configured"""
        return bool(cls.GITHUB_CLIENT_ID and cls.GITHUB_CLIENT_SECRET)
    
    @classmethod
    def validate_webhook_secret(cls) -> bool:
        """Check if webhook secret is configured"""
        return bool(cls.GITHUB_WEBHOOK_SECRET)


settings = Settings()
