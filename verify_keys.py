import os
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KeyVerifier")

load_dotenv(override=True)

def verify_groq():
    logger.info("Testing Groq Keys...")
    # Get all Groc keys
    grok_keys = [
        os.getenv("GROK_1"),
        os.getenv("GROK_2"),
        os.getenv("GROK_3"),
        os.getenv("GROK_4"),
        os.getenv("GROK_5"),
    ]
    grok_keys = [k for k in grok_keys if k]
    
    if not grok_keys:
        logger.error("❌ No Groq keys found in environment")
        return False
        
    for i, key in enumerate(grok_keys):
        try:
            logger.info(f"Testing Groq key #{i+1}...")
            client = OpenAI(
                api_key=key,
                base_url="https://api.groq.com/openai/v1"
            )
            client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10
            )
            logger.info(f"✅ Groq key #{i+1} valid")
            return True
        except Exception as e:
            logger.warning(f"❌ Groq key #{i+1} failed: {e}")
            
    return False

def verify_gemini():
    logger.info("Testing Gemini Keys...")
    gemini_keys = [
        os.getenv("GEMINI_API_KEY_1"),
        os.getenv("GEMINI_API_KEY_2"),
        os.getenv("GEMINI_API_KEY_3"),
        os.getenv("GEMINI_API_KEY_4"),
    ]
    gemini_keys = [k for k in gemini_keys if k]
    
    if not gemini_keys:
        logger.error("❌ No Gemini keys found in environment")
        return False
        
    for i, key in enumerate(gemini_keys):
        try:
            logger.info(f"Testing Gemini key #{i+1}...")
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-2.0-flash-exp")
            model.generate_content("Hello", generation_config={"max_output_tokens": 10})
            logger.info(f"✅ Gemini key #{i+1} valid")
            return True
        except Exception as e:
            logger.warning(f"❌ Gemini key #{i+1} failed: {e}")
            
    return False

if __name__ == "__main__":
    groq_ok = verify_groq()
    gemini_ok = verify_gemini()
    
    if groq_ok or gemini_ok:
        logger.info("✅ SUCCESS: At least one provider is working")
        exit(0)
    else:
        logger.error("❌ FAILURE: All keys failed")
        exit(1)
