import os
import time
import threading
import concurrent.futures
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Transient HTTP errors that are safe to retry / rotate
_TRANSIENT_HTTP_ERRORS = (
    "500", "502", "503", "504", "bad gateway", "service unavailable",
    "unavailable", "deadline_exceeded", "connection error", "connection reset",
    "timeout", "timed out", "internal server error", "server error",
)

# Priority order ordered by highest RPD/RPM quota from Google AI Studio:
# 1) Flash Lite (15 RPM, 250K TPM, 500 RPD each)
# 2) Flash & Hydrogen (5-10 RPM, 250K TPM, 20 RPD each)
# 3) Gemma 4 (30 RPM, 16K TPM, 14.4K RPD each)
_DEFAULT_GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-4-hydrogen",
    "gemini-3.6-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
]

_DEFAULT_GROQ_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "allam-2-7b",
]

_DISCOVERED_GEMINI_CACHE: Optional[list[str]] = None
_DISCOVERED_GROQ_CACHE: Optional[list[str]] = None
_DISCOVERED_OLLAMA_CACHE: Optional[list[str]] = None

_COOLDOWN_LOCK = threading.Lock()
_MODEL_COOLDOWNS: dict[str, float] = {}


def _cooldown_key(provider: str, model_name: str) -> str:
    return f"{provider.lower()}:{model_name.replace('models/', '').strip()}"


def is_model_in_cooldown(provider: str, model_name: str) -> bool:
    key = _cooldown_key(provider, model_name)
    with _COOLDOWN_LOCK:
        until = _MODEL_COOLDOWNS.get(key, 0.0)
        if until <= 0:
            return False
        if time.time() >= until:
            _MODEL_COOLDOWNS.pop(key, None)
            return False
        return True


def mark_model_rate_limited(provider: str, model_name: str, err: str = "") -> None:
    """Marks a rate-limited or unavailable model on cooldown so subsequent calls skip it automatically."""
    if provider.lower() == "ollama":
        return  # Local Ollama has no rate limit
    low = (err or "").lower()
    if any(k in low for k in ("per day", "rpd", "daily", "limit: 0")):
        ttl = 1800.0
    elif _is_rate_or_token_limit(low):
        ttl = 65.0
    else:
        ttl = 120.0
    key = _cooldown_key(provider, model_name)
    with _COOLDOWN_LOCK:
        _MODEL_COOLDOWNS[key] = time.time() + ttl


def _is_rate_or_token_limit(err: str) -> bool:
    return any(
        k in err
        for k in (
            "429", "rate_limit", "413", "tokens per minute", "tpm",
            "request too large", "resource_exhausted", "quota",
        )
    )


def _is_model_error_or_unavailable(err: str) -> bool:
    return any(
        k in err
        for k in (
            "404", "not_found", "model_not_found", "503", "504", "500",
            "unavailable", "deadline_exceeded", "does not exist",
        )
    )


def _get_gemini_api_key() -> str:
    return (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()


def discover_gemini_models(force_refresh: bool = False) -> list[str]:
    """
    Discovers available text/tool-capable Gemini models for the configured API key,
    filtering out image-only, deep-research, and deprecated 2.5 models, while
    preserving priority order.
    """
    global _DISCOVERED_GEMINI_CACHE
    if _DISCOVERED_GEMINI_CACHE is not None and not force_refresh:
        return _DISCOVERED_GEMINI_CACHE

    api_key = _get_gemini_api_key()
    if not api_key:
        return []

    excluded_substrings = (
        "-image", "nano-banana", "deep-research", "antigravity-preview",
        "omni", "gemini-2.0", "gemini-2.5-pro", "gemini-3.1-pro",
        "gemini-4-argon", "gemini-4-carbon", "computer-use", "robotics",
        "embedding", "tts", "veo", "imagen", "lyria", "transcribe", "-live",
    )
    discovered: list[str] = []
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        for m in client.models.list():
            actions = getattr(m, "supported_actions", []) or []
            if "generateContent" not in actions:
                continue
            name = (getattr(m, "name", "") or "").replace("models/", "")
            if not name or any(bad in name for bad in excluded_substrings):
                continue
            discovered.append(name)
    except Exception:
        discovered = []

    ordered: list[str] = [m for m in _DEFAULT_GEMINI_MODELS if not discovered or m in discovered]
    for m in discovered:
        if m not in ordered:
            ordered.append(m)

    _DISCOVERED_GEMINI_CACHE = ordered or list(_DEFAULT_GEMINI_MODELS)
    return _DISCOVERED_GEMINI_CACHE


def discover_groq_models(force_refresh: bool = False) -> list[str]:
    """Discovers all active text/chat Groq models, excluding audio/guard models."""
    global _DISCOVERED_GROQ_CACHE
    if _DISCOVERED_GROQ_CACHE is not None and not force_refresh:
        return _DISCOVERED_GROQ_CACHE

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return []

    excluded = ("whisper", "orpheus", "prompt-guard", "tts", "audio")
    discovered: list[str] = []
    try:
        import requests
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5,
        )
        if resp.status_code == 200:
            for item in resp.json().get("data", []):
                mid = (item.get("id") or "").strip()
                if mid and not any(b in mid.lower() for b in excluded):
                    discovered.append(mid)
    except Exception:
        discovered = []

    ordered: list[str] = [m for m in _DEFAULT_GROQ_MODELS if not discovered or m in discovered]
    for m in discovered:
        if m not in ordered:
            ordered.append(m)

    _DISCOVERED_GROQ_CACHE = ordered or list(_DEFAULT_GROQ_MODELS)
    return _DISCOVERED_GROQ_CACHE


def discover_ollama_models(force_refresh: bool = False) -> list[str]:
    """Discovers locally installed Ollama models (zero rate limits)."""
    global _DISCOVERED_OLLAMA_CACHE
    if _DISCOVERED_OLLAMA_CACHE is not None and not force_refresh:
        return _DISCOVERED_OLLAMA_CACHE

    default_local = os.getenv("OLLAMA_FALLBACK_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2:3b")).strip()
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    discovered: list[str] = []
    try:
        import requests
        resp = requests.get(f"{base_url}/api/tags", timeout=1.5)
        if resp.status_code == 200:
            for item in resp.json().get("models", []):
                name = (item.get("name") or "").strip()
                if name and "embed" not in name.lower():
                    discovered.append(name)
    except Exception:
        discovered = []

    ordered: list[str] = [default_local] if (not discovered or default_local in discovered) else []
    for m in discovered:
        if m not in ordered:
            ordered.append(m)

    _DISCOVERED_OLLAMA_CACHE = ordered or [default_local]
    return _DISCOVERED_OLLAMA_CACHE


def _build_gemini(model_name: str, temperature: float, max_tokens: int):
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = _get_gemini_api_key()
    if not api_key:
        raise ValueError("GOOGLE_API_KEY / GEMINI_API_KEY is not set.")

    timeout = float(os.getenv("LLM_TIMEOUT", "60"))
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=temperature,
        max_output_tokens=max_tokens,
        timeout=timeout,
        max_retries=0,
    )


def _build_ollama(model_name: str, temperature: float, max_tokens: int):
    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        from langchain_community.chat_models import ChatOllama

    num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    timeout = float(os.getenv("LLM_TIMEOUT", "180"))

    return ChatOllama(
        model=model_name,
        temperature=temperature,
        base_url=base_url,
        num_ctx=num_ctx,
        num_predict=max_tokens,
        keep_alive=-1,
        client_kwargs={"timeout": timeout},
    )


def _build_groq(model_name: str, temperature: float, max_tokens: int):
    from langchain_groq import ChatGroq

    timeout = float(os.getenv("LLM_TIMEOUT", "60"))
    return ChatGroq(
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout=timeout,
        max_retries=0,
    )


def _model_name_of(llm) -> str:
    return getattr(llm, "model", None) or getattr(llm, "model_name", "") or ""


def _provider_of(llm) -> str:
    cls_name = type(llm).__name__
    if "Google" in cls_name or "Gemini" in cls_name:
        return "gemini"
    if "Groq" in cls_name:
        return "groq"
    return "ollama"


def _build_provider(provider: str, temperature: float, max_tokens: int, tier: str = "heavy", model_override: Optional[str] = None):
    provider = provider.lower().strip()
    if provider == "gemini":
        fast_default = os.getenv("GEMINI_FAST_MODEL", "gemini-3.5-flash-lite")
        heavy_default = os.getenv("GEMINI_HEAVY_MODEL", "gemini-3.5-flash-lite")
        configured = os.getenv("LLM_MODEL", "")
        if model_override:
            model_name = model_override
        elif tier == "fast":
            model_name = fast_default
        elif configured and (configured.startswith("gemini") or configured.startswith("gemma")):
            model_name = configured
        else:
            model_name = heavy_default
        return _build_gemini(model_name, temperature, max_tokens)

    if provider == "groq":
        fast_default = os.getenv("GROQ_FAST_MODEL", "openai/gpt-oss-20b")
        heavy_default = os.getenv("GROQ_HEAVY_MODEL", "qwen/qwen3.8-27b")
        configured = os.getenv("LLM_MODEL", "")
        if model_override:
            model_name = model_override
        elif tier == "fast":
            model_name = fast_default
        elif configured and ":" not in configured and not configured.startswith(("gemini", "gemma")):
            model_name = configured
        else:
            model_name = heavy_default
        return _build_groq(model_name, temperature, max_tokens)

    model_name = model_override or os.getenv("OLLAMA_FALLBACK_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
    return _build_ollama(model_name, temperature, max_tokens)


def get_llm(temperature: float = 0.1, max_tokens: int = 4000, tier: str = "heavy"):
    """
    Centralized LLM initialization with priority chain & cooldown awareness:
    gemini (Google AI Studio) -> groq -> ollama (local, unlimited).
    """
    primary = os.getenv("LLM_PROVIDER", "gemini").lower().strip()
    if primary == "gemini" and _get_gemini_api_key():
        preferred = _build_provider("gemini", temperature, max_tokens, tier=tier)
        if not is_model_in_cooldown("gemini", _model_name_of(preferred)):
            return preferred
        for gm in discover_gemini_models():
            if not is_model_in_cooldown("gemini", gm):
                return _build_gemini(gm, temperature, max_tokens)
        primary = "groq" if os.getenv("GROQ_API_KEY") else "ollama"

    if primary == "groq" and os.getenv("GROQ_API_KEY"):
        for gr in discover_groq_models():
            if not is_model_in_cooldown("groq", gr):
                return _build_groq(gr, temperature, max_tokens)
        primary = "ollama"

    local_models = discover_ollama_models()
    return _build_ollama(local_models[0], temperature, max_tokens)


def get_fallback_chain(primary_llm, max_tokens: int = 4000) -> list:
    """
    Builds a full multi-model rotation & cross-provider fallback chain, skipping
    any models currently on rate-limit cooldown:
      1. All available Gemini / Gemma models
      2. All available Groq chat models
      3. All local Ollama models (zero rate limits)
    """
    if os.getenv("ENABLE_LLM_FALLBACK", "true").lower() == "false":
        return []

    temperature = getattr(primary_llm, "temperature", 0.1) or 0.1
    current_provider = _provider_of(primary_llm)
    current_model = _model_name_of(primary_llm).replace("models/", "")
    chain: list = []

    if current_provider == "gemini":
        for gm in discover_gemini_models():
            if gm != current_model and not is_model_in_cooldown("gemini", gm):
                try:
                    chain.append(_build_gemini(gm, temperature, max_tokens))
                except Exception:
                    continue

    if current_provider in ("gemini", "groq") and os.getenv("GROQ_API_KEY"):
        for gr in discover_groq_models():
            if (current_provider == "groq" and gr == current_model) or is_model_in_cooldown("groq", gr):
                continue
            try:
                chain.append(_build_groq(gr, temperature, max_tokens))
            except Exception:
                continue

    for om in discover_ollama_models():
        if current_provider == "ollama" and om == current_model:
            continue
        try:
            chain.append(_build_ollama(om, temperature, max_tokens))
        except Exception:
            continue

    if current_provider == "ollama" and os.getenv("GROQ_API_KEY"):
        for gr in discover_groq_models():
            if not is_model_in_cooldown("groq", gr):
                try:
                    chain.append(_build_groq(gr, temperature, max_tokens))
                except Exception:
                    continue

    return chain


def get_fallback_llm(primary_llm, max_tokens: int = 4000):
    """Returns the first available fallback LLM (backward-compatible helper)."""
    chain = get_fallback_chain(primary_llm, max_tokens=max_tokens)
    return chain[0] if chain else None


def needs_external_research(user_req: str) -> bool:
    """
    Fast deterministic gate replacing redundant YES/NO LLM calls in research_node.
    """
    text = (user_req or "").lower()
    research_signals = (
        "existing codebase", "integrate with", "compliance", "hipaa", "gdpr",
        "pci", "soc2", "oauth", "stripe", "webhook", "graphql", "kubernetes",
        "microservice", "migrate", "legacy", "third-party", "sdk", "documentation",
    )
    if any(sig in text for sig in research_signals):
        return True
    return len(text) > 500


def extract_text_content(value) -> str:
    """Safely extracts plain text from an AIMessage or raw str/list content payload."""
    content = getattr(value, "content", value)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    return str(content)


def _normalize_ai_response(res):
    """Normalizes list-based AIMessage.content (e.g. Gemini 3.x blocks) to plain str."""
    try:
        if hasattr(res, "content") and not isinstance(res.content, str):
            res.content = extract_text_content(res)
    except Exception:
        pass
    return res


def _log_token_usage(response, label: str = "LLM"):
    """Prints token usage metrics and generation speed."""
    try:
        usage = getattr(response, "usage_metadata", None)
        meta = getattr(response, "response_metadata", {}) or {}
        if usage:
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            tot = usage.get("total_tokens", inp + out)
            dur = meta.get("eval_duration", 0)
            speed = f" | {out / (dur / 1e9):.1f} tok/s" if dur and out else ""
            print(f"\033[96m[{label} Metrics] Prompt: {inp} | Output: {out} | Total: {tot} tokens{speed}\033[0m")
        elif "eval_count" in meta:
            inp = meta.get("prompt_eval_count", 0)
            out = meta.get("eval_count", 0)
            dur = meta.get("eval_duration", 0)
            speed = f" | {out / (dur / 1e9):.1f} tok/s" if dur and out else ""
            print(f"\033[96m[{label} Metrics] Prompt: {inp} | Output: {out} | Total: {inp+out} tokens{speed}\033[0m")
    except Exception:
        pass


def execute_tool_calls(tool_calls: list, tool_map: dict, agent_name: str = "Agent", max_output_chars: int = 4000) -> list:
    """
    Safely executes tool calls and ALWAYS returns one ToolMessage per tool_call_id
    (preventing provider 400 errors on unknown tools or tool exceptions) with capped output.
    """
    from langchain_core.messages import ToolMessage

    tool_messages = []
    for tc in tool_calls:
        name = tc.get("name", "")
        args = tc.get("args", {})
        call_id = tc.get("id", "")
        if name in tool_map:
            print(f"[{agent_name}] Calling tool: {name} with args {args}")
            try:
                raw_result = tool_map[name].invoke(args)
                result_str = raw_result if isinstance(raw_result, str) else str(raw_result)
            except Exception as e:
                result_str = f"Error executing tool '{name}': {e}"
        else:
            print(f"[{agent_name}] Called unknown tool: {name}")
            result_str = f"Error: Tool '{name}' is not available. Valid tools: {', '.join(tool_map.keys())}"

        if len(result_str) > max_output_chars:
            result_str = result_str[:max_output_chars] + "\n... [TOOL OUTPUT TRUNCATED] ..."
        tool_messages.append(ToolMessage(content=result_str, tool_call_id=call_id))
    return tool_messages


def llm_invoke_with_retry(
    llm,
    prompt,
    max_retries: int = 1,
    base_wait: int = 2,
    label: str = "LLM",
    structured_schema=None,
):
    """
    Invokes an LLM (optionally with structured output) and rotates immediately through
    Gemini models -> Groq models -> Ollama on rate-limits, 503/504, or model errors.
    """
    last_error: Optional[Exception] = None
    target = llm.with_structured_output(structured_schema) if structured_schema else llm

    for attempt in range(max_retries + 1):
        try:
            res = target.invoke(prompt)
            _normalize_ai_response(res)
            _log_token_usage(res, label=label)
            return res
        except Exception as e:
            last_error = e
            err = str(e).lower()
            if _is_rate_or_token_limit(err) or _is_model_error_or_unavailable(err):
                # Shift immediately to next model in fallback chain and place this model on cooldown
                base_cur = getattr(llm, "bound", llm)
                mark_model_rate_limited(_provider_of(base_cur), _model_name_of(base_cur), str(e))
                print(f"[{label}] {_model_name_of(llm)} unavailable/rate-limited ({str(e)[:100]}). Shifting to fallback...")
                break
            elif any(code in err for code in _TRANSIENT_HTTP_ERRORS) and attempt < max_retries:
                time.sleep(base_wait)
            else:
                break

    base_llm = getattr(llm, "bound", llm)
    for fb in get_fallback_chain(base_llm):
        prov = _provider_of(fb).upper()
        mname = _model_name_of(fb)
        try:
            fb_target = fb.with_structured_output(structured_schema) if structured_schema else fb
            print(f"[{label}] Switching to {prov} ({mname})...")
            res = fb_target.invoke(prompt)
            _normalize_ai_response(res)
            _log_token_usage(res, label=f"{label}-{prov}")
            return res
        except Exception as fb_err:
            last_error = fb_err
            fb_err_str = str(fb_err)
            if _is_rate_or_token_limit(fb_err_str.lower()) or _is_model_error_or_unavailable(fb_err_str.lower()):
                mark_model_rate_limited(prov.lower(), mname, fb_err_str)
            print(f"[{label}] {prov} ({mname}) failed: {fb_err_str[:100]}")

    raise RuntimeError(f"[{label}] All LLM providers/models failed. Last error: {last_error}")


def llm_tool_invoke_with_retry(
    llm_with_tools,
    messages,
    agent_name: str = "Agent",
    max_retries: int = 2,
    base_wait: int = 2,
    tools=None,
):
    """
    Drop-in replacement for `llm_with_tools.invoke(messages)` in multi-turn agent loops.
    Handles Groq malformed tool calls, history pruning, and instant multi-model rotation:
    Gemini models -> Groq models -> Local Ollama.
    """
    from langchain_core.messages import AIMessage, HumanMessage
    import re

    # Keep conversation bounded to prevent token explosion across 15 turns
    if len(messages) > 14:
        messages[:] = [messages[0], messages[1]] + messages[-10:]

    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            res = llm_with_tools.invoke(messages)
            _normalize_ai_response(res)
            _log_token_usage(res, label=agent_name)
            return res
        except Exception as e:
            last_error = e
            err = str(e).lower()
            if "tool_use_failed" in err or "attempted to call tool" in err:
                print(f"[{agent_name}] Tool formatting error from LLM. Extracting payload if present...")
                error_str = str(e)
                try:
                    match = re.search(r"'failed_generation':\s*('|\")(.*)('|\")\s*\}\s*\}", error_str, re.DOTALL)
                    if match:
                        raw_json_str = match.group(2).replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
                        return AIMessage(content=f"```json\n{raw_json_str}\n```")
                except Exception:
                    pass
                messages.append(HumanMessage(
                    content="SYSTEM NOTICE: Do not output markdown code blocks or hallucinated tools like 'json'. You must strictly invoke one of the provided function tools directly."
                ))
                time.sleep(1)
                continue
            elif _is_rate_or_token_limit(err) or _is_model_error_or_unavailable(err):
                if len(messages) > 4:
                    messages[:] = [messages[0], messages[1]] + messages[-2:]
                base_cur = getattr(llm_with_tools, "bound", llm_with_tools)
                mark_model_rate_limited(_provider_of(base_cur), _model_name_of(base_cur), str(e))
                print(f"[{agent_name}] Rate-limited/unavailable ({str(e)[:90]}). Rotating to next model...")
                break
            elif any(code in err for code in _TRANSIENT_HTTP_ERRORS):
                time.sleep(base_wait)
            else:
                break

    bound = getattr(llm_with_tools, "bound", llm_with_tools)
    bound_tools = tools or getattr(llm_with_tools, "kwargs", {}).get("tools")
    for fb in get_fallback_chain(bound):
        prov = _provider_of(fb).upper()
        mname = _model_name_of(fb)
        try:
            target = fb.bind_tools(bound_tools) if bound_tools else fb
            print(f"[{agent_name}] Switching to {prov} ({mname})...")
            res = target.invoke(messages)
            _normalize_ai_response(res)
            _log_token_usage(res, label=f"{agent_name}-{prov}")
            return res
        except Exception as fb_err:
            last_error = fb_err
            fb_err_str = str(fb_err)
            if _is_rate_or_token_limit(fb_err_str.lower()) or _is_model_error_or_unavailable(fb_err_str.lower()):
                mark_model_rate_limited(prov.lower(), mname, fb_err_str)
            print(f"[{agent_name}] {prov} ({mname}) failed: {fb_err_str[:100]}")

    raise RuntimeError(f"[{agent_name}] All LLM providers/models failed. Last error: {last_error}")


def safe_web_search(query: str, timeout: int = 5) -> str:
    """
    Executes DuckDuckGo search with a strict timeout to prevent indefinite hangs.
    """
    from langchain_community.tools.ddg_search.tool import DuckDuckGoSearchResults

    search_tool = DuckDuckGoSearchResults(backend="html")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(search_tool.invoke, {"query": query})
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return "Search timed out. Proceeding without web results."
        except Exception as e:
            return f"Search failed: {e}"


def run_tool_loop_with_json_fallback(
    llm,
    tools_list: list,
    messages: list,
    agent_name: str = "Agent",
    max_turns: int = 8,
    nudge_after_turn: int = 4,
) -> str:
    """
    Runs a bounded tool-calling loop and guarantees a final JSON text response.
    If the model exhausts tool turns without emitting JSON, forces one final
    tool-free invocation so code-generation nodes always receive file payloads.
    """
    from langchain_core.messages import AIMessage, HumanMessage

    llm_with_tools = llm.bind_tools(tools_list)
    tool_map = {t.name: t for t in tools_list}
    wrote_via_tool = False

    for turn in range(max_turns):
        if turn == nudge_after_turn:
            if wrote_via_tool:
                messages.append(HumanMessage(
                    content=(
                        "You have written files using `write_file`. Finish any remaining files now, "
                        'or output your final JSON response (`{"terminal_commands": [...], "files": []}`) in plain text wrapped in ```json ... ```.'
                    )
                ))
            else:
                messages.append(HumanMessage(
                    content=(
                        "Stop calling directory/inspection tools! Use `write_file` right now to write each source file directly to disk, "
                        'or output your final JSON response ({"terminal_commands": [...], "files": [...]}) in plain text wrapped in ```json ... ```.'
                    )
                ))

        try:
            response = llm_tool_invoke_with_retry(
                llm_with_tools, messages, agent_name=agent_name, tools=tools_list
            )
        except Exception as invoke_e:
            error_str = str(invoke_e)
            if "failed_generation" in error_str:
                fg_idx = error_str.find("'failed_generation': '")
                if fg_idx != -1:
                    start_idx = fg_idx + len("'failed_generation': '")
                    end_idx = error_str.rfind("'}}")
                    if end_idx == -1 or end_idx <= start_idx:
                        end_idx = error_str.rfind("'")
                    try:
                        raw_fg = error_str[start_idx:end_idx].replace("\\n", "\n").replace("\\'", "'")
                        failed_gen = json.loads(raw_fg, strict=False)
                        args = failed_gen.get("arguments", {})

                        class DummyResponse:
                            content = json.dumps(args) if isinstance(args, dict) else str(args)
                            tool_calls = []

                        response = DummyResponse()
                    except Exception:
                        raise invoke_e
                else:
                    raise invoke_e
            else:
                raise invoke_e

        messages.append(response)

        if not getattr(response, "tool_calls", None):
            break

        resp_text = extract_text_content(response)
        if "```json" in resp_text and '"files"' in resp_text:
            break

        if any(tc.get("name") == "write_file" for tc in (response.tool_calls or [])):
            wrote_via_tool = True

        messages.extend(execute_tool_calls(response.tool_calls, tool_map, agent_name=agent_name))

    final_content = ""
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage) and getattr(msg, "type", "") != "ai":
            continue
        text = extract_text_content(msg)
        if text and ("```json" in text or ('"files"' in text and '"terminal_commands"' in text)):
            # Avoid accepting a premature empty files: [] response if write_file wasn't used
            if not wrote_via_tool and ('"files": []' in text or '"files":[]' in text):
                continue
            final_content = text
            break

    if not final_content:
        if wrote_via_tool:
            return '{"terminal_commands": [], "files": []}'
        print(f"[{agent_name}] Tool loop finished without non-empty JSON; forcing tool-free JSON generation.")
        messages.append(HumanMessage(
            content=(
                "STOP calling tools immediately. Output ONLY the valid JSON object matching "
                '{"terminal_commands": [...], "files": [{"path": "...", "content": "..."}]} '
                "wrapped in ```json ... ```. You MUST include full, runnable source files in \"files\" "
                "(do NOT return an empty \"files\": [] array). Do not include any prose outside the JSON block."
            )
        ))
        final_resp = llm_invoke_with_retry(llm, messages, label=f"{agent_name} (Final JSON)")
        final_content = extract_text_content(final_resp)

    return final_content
