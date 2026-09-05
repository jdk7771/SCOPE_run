# about habitat scene
INVALID_SCENE_ID = []

# about chatgpt api
import os

# Defaults to the local Ollama-served VLM (unchanged behavior). Set
# USE_REAL_OPENAI=1 together with a real OPENAI_API_KEY to point at the
# actual OpenAI API instead; OLLAMA_ENDPOINT keeps overriding the local
# address whenever USE_REAL_OPENAI is not set.
_USE_REAL_OPENAI = os.environ.get("USE_REAL_OPENAI", "0") == "1"
_REAL_OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

if _USE_REAL_OPENAI and _REAL_OPENAI_KEY:
    # Defaults to the real OpenAI API; REAL_OPENAI_BASE_URL lets this point
    # at an OpenAI-compatible relay/reseller endpoint instead when set.
    END_POINT = os.environ.get("REAL_OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_KEY = _REAL_OPENAI_KEY
else:
    END_POINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11435/v1")
    OPENAI_KEY = "ollama"

