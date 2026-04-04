"""
AI Project - Main Entry Point (Python)
Supports switching between different AI models via OpenRouter.
"""

import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize OpenRouter client
client = OpenAI(
    base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# Model configurations
MODELS = {
    "hermes": os.getenv("DEFAULT_MODEL", "nousresearch/hermes-3-llama-3.1-70b"),
    "claude": "anthropic/claude-3.5-sonnet",
    "qwen": "qwen/qwen-2.5-72b-instruct",
    "gpt4": "openai/gpt-4o",
}


def chat(message: str, model: str = "hermes", system_prompt: str = None) -> str:
    """
    Send a message to the AI model and get response.
    
    Args:
        message: User message
        model: Model key from MODELS dict (hermes, claude, qwen, gpt4)
        system_prompt: Optional system prompt
    
    Returns:
        AI response text
    """
    model_name = MODELS.get(model, MODELS["hermes"])
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})
    
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.7,
        max_tokens=2000,
    )
    
    return response.choices[0].message.content


def list_available_models() -> dict:
    """Return available model configurations."""
    return MODELS


# Example usage
if __name__ == "__main__":
    print("Available models:", list(list_available_models().keys()))
    
    # Test with Hermes
    response = chat("Hej! Vad heter du och vad kan du hjälpa mig med?", model="hermes")
    print(f"\n[Hermes]: {response}")
    
    # Example with system prompt
    response = chat(
        "Explain the benefits of using PostgreSQL indexes",
        model="hermes",
        system_prompt="You are a database expert. Keep answers concise."
    )
    print(f"\n[Hermes with system prompt]: {response}")
