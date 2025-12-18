from fastapi import HTTPException


class GitHubAPIError(HTTPException):
    """GitHub API request failed"""
    def __init__(self, detail: str, status_code: int = 500):
        super().__init__(status_code=status_code, detail=detail)


class AuthenticationError(HTTPException):
    """Authentication failed"""
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(status_code=401, detail=detail)


class WebhookValidationError(HTTPException):
    """Webhook signature validation failed"""
    def __init__(self, detail: str = "Invalid webhook signature"):
        super().__init__(status_code=401, detail=detail)


class MissingConfigurationError(HTTPException):
    """Required configuration is missing"""
    def __init__(self, detail: str):
        super().__init__(status_code=500, detail=detail)


class AIGenerationError(Exception):
    """AI content generation failed"""
    pass
