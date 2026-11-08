import os
import time
from langchain_groq import ChatGroq

# Transient HTTP errors that are safe to retry with a short backoff
_TRANSIENT_HTTP_ERRORS = ("500", "502", "503", "504", "bad gateway", "service unavailable",
                          "connection error", "connection reset", "timeout", "internal server error", "server error")

def get_llm(temperature: float = 0.1, max_tokens: int = 4000):
    """
    Centralized LLM initialization.
    Reads the model from the environment variable LLM_MODEL.
    Uses LLM_PROVIDER to determine the backend (default: groq, alternative: ollama).
    """
    model_name = os.getenv("LLM_MODEL", "llama-3.1-70b-versatile")
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    
    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            from langchain_community.chat_models import ChatOllama

        num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        return ChatOllama(
            model=model_name,
            temperature=temperature,
            base_url=base_url,
            num_ctx=num_ctx,
            # Keep the connection alive so rapid sequential calls don't get 502s
            keep_alive=-1,
        )
    else:
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens
        )


def llm_invoke_with_retry(llm, prompt, max_retries: int = 5, base_wait: int = 15):
    """
    Invokes an LLM with automatic retry on both:
    - 429 rate-limit errors  → exponential backoff (base_wait * attempt seconds)
    - 502/503/504 transient errors → short fixed backoff (5s) to ride out glitches
    All other errors are raised immediately.
    """
    for attempt in range(max_retries):
        try:
            return llm.invoke(prompt)
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate_limit" in err:
                wait = base_wait * (attempt + 1)
                print(f"[LLM] Rate limited (attempt {attempt+1}/{max_retries}). Waiting {wait}s...")
                time.sleep(wait)
            elif any(code in err for code in _TRANSIENT_HTTP_ERRORS):
                wait = 5 * (attempt + 1)
                print(f"[LLM] Transient HTTP error (attempt {attempt+1}/{max_retries}): {str(e)[:120]}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"LLM call failed after {max_retries} retries.")


def llm_tool_invoke_with_retry(llm_with_tools, messages, agent_name: str = "Agent", max_retries: int = 4):
    """
    Drop-in replacement for `llm_with_tools.invoke(messages)` in multi-turn agent loops.
    Retries on transient Ollama 502/503/504 errors with escalating 5s backoff.
    Non-transient errors are re-raised immediately so the caller can handle them.
    """
    for attempt in range(max_retries):
        try:
            return llm_with_tools.invoke(messages)
        except Exception as e:
            err = str(e).lower()
            if any(code in err for code in _TRANSIENT_HTTP_ERRORS) and attempt < max_retries - 1:
                wait = 5 * (attempt + 1)
                print(f"[{agent_name}] Transient LLM error (attempt {attempt+1}/{max_retries}): {str(e)[:100]}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"[{agent_name}] LLM tool call failed after {max_retries} retries.")


import concurrent.futures
from langchain_community.tools.ddg_search.tool import DuckDuckGoSearchResults

def safe_web_search(query: str, timeout: int = 5) -> str:
    """
    Executes DuckDuckGo search with a strict timeout to prevent indefinite hangs.
    """
    search_tool = DuckDuckGoSearchResults(backend="html")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(search_tool.invoke, {"query": query})
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return "Search timed out. Proceeding without web results."
        except Exception as e:
            return f"Search failed: {e}"
