import os
import logging
from typing import Dict, Any, Optional, List
from enum import Enum
import random

# Grok uses OpenAI-compatible API
from openai import OpenAI
import google.generativeai as genai

logger = logging.getLogger("AIOrchestrator")
logger.setLevel(logging.INFO)

# ============================================
# MULTI-KEY CONFIGURATION
# ============================================

class ProviderType(Enum):
    GROK = "grok"
    GEMINI = "gemini"

# Load all API keys from environment
GROK_KEYS = [
    os.getenv("GROK_1"),
    os.getenv("GROK_2"),
    os.getenv("GROK_3"),
    os.getenv("GROK_4"),
    os.getenv("GROK_5"),
]
GROK_KEYS = [k for k in GROK_KEYS if k]  # Filter out None values

GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
    os.getenv("GEMINI_API_KEY_4"),
]
GEMINI_KEYS = [k for k in GEMINI_KEYS if k]  # Filter out None values

# Key rotation state
class KeyRotator:
    def __init__(self, keys: List[str], provider: str):
        self.keys = keys
        self.provider = provider
        self.current_index = 0
        
    def get_next(self) -> Optional[str]:
        """Get next API key in rotation"""
        if not self.keys:
            return None
        key = self.keys[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.keys)
        logger.info(f"🔑 Using {self.provider} key #{self.current_index + 1}/{len(self.keys)}")
        return key
    
    def reset(self):
        """Reset to first key"""
        self.current_index = 0

# Initialize rotators
grok_rotator = KeyRotator(GROK_KEYS, "Grok")
gemini_rotator = KeyRotator(GEMINI_KEYS, "Gemini")


# ============================================
# AI ORCHESTRATOR
# ============================================

class AIOrchestrator:
    """
    Multi-model AI orchestrator with automatic failover and key rotation.
    
    Flow:
    1. Try Groq keys (round-robin through 5 keys) - Fast Llama inference
    2. If all Groq keys fail, try Gemini keys (round-robin through 3 keys)
    3. If all fail, raise error
    """
    
    def __init__(self):
        self.grok_enabled = len(GROK_KEYS) > 0
        self.gemini_enabled = len(GEMINI_KEYS) > 0
        
        logger.info(f"🤖 AI Orchestrator initialized:")
        logger.info(f"   Groq keys: {len(GROK_KEYS)}")
        logger.info(f"   Gemini keys: {len(GEMINI_KEYS)}")
    
    def _try_grok(self, prompt: str, response_format: Optional[str] = None) -> Optional[str]:
        """Try Groq API (fast Llama inference) with current key rotation"""
        if not self.grok_enabled:
            return None
        
        # Try each Groq key
        for attempt in range(len(GROK_KEYS)):
            api_key = grok_rotator.get_next()
            try:
                logger.info(f"🤖 Attempting Groq/Llama (attempt {attempt + 1}/{len(GROK_KEYS)})")
                
                client = OpenAI(
                    api_key=api_key,
                    base_url="https://api.groq.com/openai/v1"  # Groq endpoint
                )
                
                messages = [{"role": "user", "content": prompt}]
                
                # Use Llama 3.3 70B (fast and capable)
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=0.7,
                )
                
                result = response.choices[0].message.content
                logger.info(f"✅ Groq/Llama succeeded with key #{attempt + 1}")
                return result
               
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"❌ Groq key #{attempt + 1} failed: {error_msg[:150]}")
                logger.debug(f"Full Groq error: {error_msg}")
                continue
        
        logger.error(f"❌ All {len(GROK_KEYS)} Groq keys failed")
        return None
    
    def _try_gemini(self, prompt: str, response_format: Optional[str] = None) -> Optional[str]:
        """Try Gemini API with current key rotation"""
        if not self.gemini_enabled:
            return None
        
        # Try each Gemini key
        for attempt in range(len(GEMINI_KEYS)):
            api_key = gemini_rotator.get_next()
            try:
                logger.info(f"🤖 Attempting Gemini (attempt {attempt + 1}/{len(GEMINI_KEYS)})")
                
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-2.0-flash-exp")
                
                generation_config = {}
                if response_format == "json":
                    generation_config["response_mime_type"] = "application/json"
                
                response = model.generate_content(prompt, generation_config=generation_config)
                result = response.text
                
                logger.info(f"✅ Gemini succeeded with key #{attempt + 1}")
                return result
                
            except Exception as e:
                logger.warning(f"❌ Gemini key #{attempt + 1} failed: {str(e)[:100]}")
                continue
        
        logger.error(f"❌ All {len(GEMINI_KEYS)} Gemini keys failed")
        return None
    
    def generate(self, prompt: str, response_format: Optional[str] = None, max_retries: int = 1) -> str:
        """
        Generate AI response with automatic failover.
        
        Args:
            prompt: The input prompt
            response_format: Optional format ("json" or None)
            max_retries: Number of full retry cycles
            
        Returns:
            AI-generated response
            
        Raises:
            Exception: If all providers and retries fail
        """
        for retry in range(max_retries):
            if retry > 0:
                logger.info(f"🔄 Retry {retry + 1}/{max_retries}")
            
            # Step 1: Try Grok (all keys)
            if self.grok_enabled:
                result = self._try_grok(prompt, response_format)
                if result:
                    return result
            
            # Step 2: Fallback to Gemini (all keys)
            if self.gemini_enabled:
                result = self._try_gemini(prompt, response_format)
                if result:
                    return result
        
        # All attempts failed
        raise Exception(
            f"AI generation failed after trying "
            f"{len(GROK_KEYS)} Groq keys and {len(GEMINI_KEYS)} Gemini keys "
            f"across {max_retries} retry cycles"
        )


# Global orchestrator instance
orchestrator = AIOrchestrator()


# ============================================
# PUBLIC API
# ============================================

def generate_content(prompt: str, response_format: Optional[str] = None) -> str:
    """
    Main API for generating AI content with automatic multi-model failover.
    
    Args:
        prompt: The input prompt
        response_format: Optional format ("json" or None)
        
    Returns:
        AI-generated response string
    """
    return orchestrator.generate(prompt, response_format)
