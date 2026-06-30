import os
from dotenv import load_dotenv
from crewai.llms.providers.openai_compatible import OpenAICompatibleCompletion

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    raise ValueError("Missing OPENROUTER_API_KEY in .env file!")

def create_openrouter_llm(model_name: str):
    """Create an OpenRouter-compatible LLM for CrewAI"""
    return OpenAICompatibleCompletion(
        model=model_name,
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        temperature=0.7
    )

# Create LLM instances
DATA_LLM = create_openrouter_llm("google/gemma-2-9b-it:free")
SPEED_LLM = create_openrouter_llm("meta-llama/llama-3.1-8b-instruct:free")
REASONING_LLM = create_openrouter_llm("mistralai/mistral-7b-instruct:free")

# Model strings for fallback
DATA_MODEL = "openrouter/google/gemma-2-9b-it:free"
SPEED_MODEL = "openrouter/meta-llama/llama-3.1-8b-instruct:free"
REASONING_MODEL = "openrouter/mistralai/mistral-7b-instruct:free"