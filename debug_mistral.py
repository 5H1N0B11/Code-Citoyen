import os
import asyncio
import logging
from mistralai import Mistral

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_mistral_simple():
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        logger.error("MISTRAL_API_KEY not found.")
        return

    client = Mistral(api_key=api_key)
    logger.info("Mistral client initialized.")

    messages = [
        {"role": "user", "content": "Hello, classify this: 'The sky is blue'. Answer with one word."}
    ]

    try:
        logger.info("Sending async request...")
        response = await client.chat.complete_async(
            model="mistral-small-latest",
            messages=messages,
            temperature=0.0
        )
        logger.info(f"Response received: {response.choices[0].message.content}")
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_mistral_simple())
