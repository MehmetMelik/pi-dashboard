"""Optional AI summarization via local Ollama."""

import httpx
from app.config import OLLAMA_URL, OLLAMA_MODEL, OLLAMA_ENABLED
from app.database import get_unsummarized_articles, set_ai_summary


async def is_available() -> bool:
    if not OLLAMA_ENABLED:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


async def summarize_one() -> bool:
    """Summarize one unsummarized article. Returns True if work was done."""
    articles = get_unsummarized_articles(limit=1)
    if not articles:
        return False

    article = articles[0]
    text = article["title"]
    if article.get("summary"):
        text += f" — {article['summary']}"

    prompt = f"Summarize this news article in one concise sentence (max 20 words). Only output the summary, nothing else.\n\n{text}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 50},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            summary = data.get("response", "").strip()
            if summary:
                set_ai_summary(article["id"], summary)
                return True
    except Exception as e:
        print(f"[ollama] summarize error: {e}")
    return False
