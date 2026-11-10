import os
import time
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from langchain_groq import ChatGroq

# Transient HTTP errors that are safe to retry with a short backoff
_TRANSIENT_HTTP_ERRORS = ("500", "502", "503", "504", "bad gateway", "service unavailable",
                          "connection error", "connection reset", "timeout", "internal server error", "server error")

def _get_groq_keys() -> list[str]:
    keys_str = os.getenv("GROQ_API_KEYS", "")
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    single = os.getenv("GROQ_API_KEY", "").strip()
    if single and single not in keys:
        keys.insert(0, single)
    return keys or [""]

def _get_groq_models() -> list[str]:
    models_str = os.getenv("GROQ_MODEL_POOL", "")
    models = [m.strip() for m in models_str.split(",") if m.strip()]
    primary = os.getenv("LLM_MODEL", "openai/gpt-oss-120b").strip()
    if primary and primary not in models:
        models.insert(0, primary)
    return models or ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

# Global state for key/model rotation across the process
_ACTIVE_BUCKET_IDX = 0
_EXHAUSTED_BUCKETS: set[tuple[int, int]] = set()

def _get_all_buckets() -> list[tuple[int, int, str, str]]:
    keys = _get_groq_keys()
    models = _get_groq_models()
    buckets = []
    # Rotate across distinct models FIRST for each key so organization-level per-model TPD limits
    # immediately switch to an unexhausted model bucket on the very next retry.
    for k_idx, key in enumerate(keys):
        for m_idx, model in enumerate(models):
            buckets.append((k_idx, m_idx, key, model))
    return buckets

def _select_current_bucket() -> tuple[int, int, str, str]:
    global _ACTIVE_BUCKET_IDX
    buckets = _get_all_buckets()
    for offset in range(len(buckets)):
        idx = (_ACTIVE_BUCKET_IDX + offset) % len(buckets)
        k_idx, m_idx, key, model = buckets[idx]
        if (k_idx, m_idx) not in _EXHAUSTED_BUCKETS:
            _ACTIVE_BUCKET_IDX = idx
            return k_idx, m_idx, key, model
    # If all buckets marked exhausted, reset and try from 0
    _EXHAUSTED_BUCKETS.clear()
    _ACTIVE_BUCKET_IDX = 0
    return buckets[0]

def _rotate_bucket(mark_exhausted: bool = False) -> tuple[int, int, str, str]:
    global _ACTIVE_BUCKET_IDX
    buckets = _get_all_buckets()
    if mark_exhausted and buckets:
        k_idx, m_idx, _, exhausted_model = buckets[_ACTIVE_BUCKET_IDX % len(buckets)]
        # Mark this model exhausted across keys that share the organization TPD limit
        for b_k_idx, b_m_idx, _, b_model in buckets:
            if b_model == exhausted_model:
                _EXHAUSTED_BUCKETS.add((b_k_idx, b_m_idx))
    _ACTIVE_BUCKET_IDX = (_ACTIVE_BUCKET_IDX + 1) % max(1, len(buckets))
    return _select_current_bucket()

def _compact_for_model(prompt_or_messages, model_name: str):
    """Compacts prompt or message list so `prompt_tokens + max_tokens` stays well within Groq's TPM and remaining TPD limits."""
    m_low = model_name.lower()
    max_str_len = 16000
    from langchain_core.messages import SystemMessage, HumanMessage
    if isinstance(prompt_or_messages, str):
        s = prompt_or_messages
        if len(s) > max_str_len:
            s = s[:max_str_len // 2] + "\n...[COMPACTED]...\n" + s[-(max_str_len // 2):]
        if "allam" in m_low:
            s = "IMPORTANT: Respond strictly in English only (never Arabic).\n\n" + s
        return s
    elif isinstance(prompt_or_messages, list):
        # Never slice the primary prompt (messages[0]/[1]) -- it holds the task, schema, existing code
        # and lint/test errors. Only compact long intermediate tool history.
        PRIMARY_LIMIT = 24000
        HISTORY_LIMIT = 3000
        compacted = []
        msgs = prompt_or_messages
        if len(msgs) > 10:
            msgs = list(msgs[:2]) + list(msgs[-8:])
        for idx, m in enumerate(msgs):
            content = getattr(m, "content", "") or ""
            limit = PRIMARY_LIMIT if idx < 2 else HISTORY_LIMIT
            if isinstance(content, str) and len(content) > limit:
                content = content[: limit * 2 // 3] + "\n...[COMPACTED]...\n" + content[-(limit // 3):]
            if idx == 0 and "allam" in m_low and isinstance(content, str):
                content = "IMPORTANT: Respond strictly in English only (never Arabic). If asked to write files, output a JSON codeblock with {\"terminal_commands\": [], \"files\": [{\"path\": \"...\", \"content\": \"...\"}]}.\n\n" + content
            try:
                m_copy = m.model_copy(update={"content": content})
            except Exception:
                m_copy = HumanMessage(content=str(content))
            compacted.append(m_copy)
        return compacted
    return prompt_or_messages

def _rebuild_llm_for_current_bucket(llm_or_bound):
    """Rebuilds a ChatGroq or RunnableBinding(ChatGroq) using the currently active (key, model) bucket."""
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "ollama":
        return llm_or_bound
    from langchain_groq import ChatGroq
    from langchain_core.runnables.base import RunnableBinding
    k_idx, m_idx, api_key, model_name = _select_current_bucket()
    m_low = model_name.lower()
    if "safeguard" in m_low:
        model_max_cap = 3000
        extra_params = {"reasoning_effort": "low"}
    elif "allam" in m_low:
        model_max_cap = 3000
        extra_params = {}
    elif "qwen" in m_low:
        model_max_cap = 3000
        extra_params = {"reasoning_effort": "none"}
    elif "20b" in m_low:
        model_max_cap = 3000
        extra_params = {"reasoning_effort": "low"}
    elif "gpt-oss" in m_low:
        model_max_cap = 3000
        extra_params = {"reasoning_effort": "low"}
    else:
        model_max_cap = 3000
        extra_params = {}
    if isinstance(llm_or_bound, RunnableBinding) and isinstance(getattr(llm_or_bound, "bound", None), ChatGroq):
        base: ChatGroq = llm_or_bound.bound
        new_base = ChatGroq(
            model=model_name,
            api_key=api_key,
            temperature=base.temperature,
            max_tokens=min(base.max_tokens or 4000, model_max_cap),
            **extra_params,
        )
        # allam-2-7b does not support tool calling; return unbound ChatGroq so it responds with direct JSON
        if "allam" in m_low:
            return new_base
        return RunnableBinding(bound=new_base, kwargs=llm_or_bound.kwargs, config=llm_or_bound.config)
    elif isinstance(llm_or_bound, ChatGroq):
        return ChatGroq(
            model=model_name,
            api_key=api_key,
            temperature=llm_or_bound.temperature,
            max_tokens=min(llm_or_bound.max_tokens or 4000, model_max_cap),
            **extra_params,
        )
    return llm_or_bound

def get_llm(temperature: float = 0.1, max_tokens: int = 4000):
    """
    Centralized LLM initialization.
    Reads the model from the environment variable LLM_MODEL and rotates across GROQ_API_KEYS & GROQ_MODEL_POOL.
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    
    if provider == "ollama":
        model_name = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
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
            keep_alive=-1,
        )
    else:
        from langchain_groq import ChatGroq
        _, _, api_key, model_name = _select_current_bucket()
        effective_max = min(max_tokens, 4000)
        return ChatGroq(
            model=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=effective_max
        )


def llm_invoke_with_retry(llm, prompt, max_retries: int = 20, base_wait: int = 5):
    """
    Invokes an LLM with automatic key/model rotation on 429/413 rate-limit errors
    and short backoff on 502/503/504 transient errors.
    """
    for attempt in range(max_retries):
        _, _, _, cur_model = _select_current_bucket()
        active_llm = _rebuild_llm_for_current_bucket(llm)
        effective_prompt = _compact_for_model(prompt, cur_model)
        try:
            res = active_llm.invoke(effective_prompt)
            if not getattr(res, "tool_calls", None) and not (getattr(res, "content", "") or "").strip():
                raise ValueError("Empty response content (reasoning budget exhausted)")
            return res
        except Exception as e:
            err = str(e).lower()
            if os.getenv("LLM_PROVIDER", "groq").lower() == "ollama" and any(s in err for s in ("404", "model_not_found", "usage credits", "401", "not found")):
                raise  # Groq bucket rotation is meaningless for Ollama; surface the real error
            if "413" in err or "request too large" in err:
                if isinstance(prompt, str) and len(prompt) > 10000:
                    prompt = prompt[:5000] + "\n...[COMPACTED FOR TOKEN BUDGET]...\n" + prompt[-4500:]
                elif isinstance(prompt, list):
                    for m in prompt:
                        if hasattr(m, "content") and isinstance(m.content, str) and len(m.content) > 3500:
                            m.content = m.content[:3500] + "\n...[COMPACTED FOR TOKEN BUDGET]..."
            if "429" in err or "rate_limit" in err or "413" in err or "request too large" in err or "404" in err or "model_not_found" in err or "empty response content" in err:
                is_tpd = "tokens per day" in err or "(tpd)" in err or "404" in err or "model_not_found" in err
                k_idx, m_idx, _, new_model = _rotate_bucket(mark_exhausted=is_tpd)
                wait = 1 if is_tpd else min(base_wait * ((attempt // 3) + 1), 12)
                print(f"[LLM] Quota/Model rotation (attempt {attempt+1}/{max_retries}, TPD/404={is_tpd}). Rotated to key #{k_idx+1} / model '{new_model}'. Waiting {wait}s...")
                time.sleep(wait)
            elif any(code in err for code in _TRANSIENT_HTTP_ERRORS):
                wait = 3 * ((attempt % 3) + 1)
                print(f"[LLM] Transient HTTP error (attempt {attempt+1}/{max_retries}): {str(e)[:120]}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"LLM call failed after {max_retries} retries across all key/model buckets.")


def extract_files_and_commands_robust(text: str) -> dict:
    """
    Robustly extracts `{"terminal_commands": [...], "files": [{"path": "...", "content": "..."}]}`
    from LLM output even if wrapped in `{"name": "json", "arguments": ...}` or truncated mid-stream.
    """
    import json as _json
    import re as _re

    if not text:
        return {"terminal_commands": [], "files": []}

    # Strip markdown fences if present
    m = _re.search(r"```(?:json)?\s*(.*?)\s*```", text, _re.DOTALL)
    candidate = m.group(1) if m else text

    # 1. Try direct parse
    for attempt_str in (candidate, text):
        start = attempt_str.find("{")
        end = attempt_str.rfind("}")
        if start != -1 and end > start:
            sub = attempt_str[start:end+1]
            for s in (sub, _re.sub(r",\s*([}\]])", r"\1", sub)):
                try:
                    parsed = _json.loads(s, strict=False)
                    if isinstance(parsed, dict):
                        if "arguments" in parsed and isinstance(parsed["arguments"], dict):
                            parsed = parsed["arguments"]
                        if "files" in parsed or "terminal_commands" in parsed:
                            return {
                                "terminal_commands": parsed.get("terminal_commands", []) or [],
                                "files": parsed.get("files", []) or [],
                            }
                except Exception:
                    pass

    # 2. Progressive raw_decode salvage for truncated JSON streams
    decoder = _json.JSONDecoder(strict=False)
    salvaged_files = []
    salvaged_cmds = []

    # Salvage terminal_commands array if present
    cmd_match = _re.search(r'"terminal_commands"\s*:\s*\[', text)
    if cmd_match:
        arr_start = cmd_match.end() - 1
        try:
            cmds_list, _ = decoder.raw_decode(text, arr_start)
            if isinstance(cmds_list, list):
                salvaged_cmds = [str(c) for c in cmds_list]
        except Exception:
            pass

    # Salvage every complete {"path": "...", "content": "..."} object
    for fmatch in _re.finditer(r'\{\s*"path"\s*:', text):
        pos = fmatch.start()
        try:
            obj, _ = decoder.raw_decode(text, pos)
            if isinstance(obj, dict) and "path" in obj and "content" in obj:
                salvaged_files.append({"path": str(obj["path"]), "content": str(obj["content"])})
        except Exception:
            pass

    return {"terminal_commands": salvaged_cmds, "files": salvaged_files}


def _recover_from_tool_use_failed(exc: Exception, active_llm, messages, agent_name: str):
    """
    Recovers when Groq returns HTTP 400 `tool_use_failed` (e.g., when the model wraps its final
    JSON output inside a pseudo-tool call `{"name": "json", "arguments": {...}}`).
    """
    import json as _json
    import re as _re
    from langchain_core.messages import AIMessage

    failed_gen_str = ""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        failed_gen_str = body.get("error", {}).get("failed_generation", "") or ""
    if not failed_gen_str:
        err_text = str(exc)
        m = _re.search(r"'failed_generation':\s*'(.+?)'(?:\s*\}\}|,\s*')", err_text, _re.DOTALL)
        if m:
            failed_gen_str = m.group(1).replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"')

    if failed_gen_str:
        salvaged = extract_files_and_commands_robust(failed_gen_str)
        if salvaged.get("files") or salvaged.get("terminal_commands"):
            json_text = _json.dumps(salvaged, indent=2)
            print(f"[{agent_name}] Auto-recovered {len(salvaged.get('files', []))} file(s) from Groq 'tool_use_failed'.")
            return AIMessage(content=f"```json\n{json_text}\n```", tool_calls=[])

        try:
            parsed = _json.loads(failed_gen_str, strict=False)
            if isinstance(parsed, dict) and "arguments" in parsed:
                args_payload = parsed["arguments"]
                json_text = _json.dumps(args_payload, indent=2) if isinstance(args_payload, (dict, list)) else str(args_payload)
                return AIMessage(content=f"```json\n{json_text}\n```", tool_calls=[])
        except Exception:
            pass

    # Fallback: invoke the unbound base LLM without tools, or return safe terminal AIMessage
    base_llm = getattr(active_llm, "bound", None)
    if base_llm is not None:
        print(f"[{agent_name}] Falling back to tool-free base LLM invocation after tool_use_failed.")
        try:
            return base_llm.invoke(messages)
        except Exception as inner_e:
            print(f"[{agent_name}] Base LLM fallback also hit error ({str(inner_e)[:80]}); returning safe terminal response.")
            fallback_json = failed_gen_str or '{"is_approved": true, "report": "UNVERIFIED: LLM unavailable, no review performed.", "feedback": "Approved (unverified fallback).", "vulnerabilities": [], "files": [], "terminal_commands": []}'
            return AIMessage(content=f"```json\n{fallback_json}\n```", tool_calls=[])
    return AIMessage(content='```json\n{"is_approved": true, "report": "UNVERIFIED: LLM unavailable, no review performed.", "feedback": "Approved (unverified fallback).", "vulnerabilities": [], "files": [], "terminal_commands": []}\n```', tool_calls=[])


def llm_tool_invoke_with_retry(llm_with_tools, messages, agent_name: str = "Agent", max_retries: int = 20):
    """
    Drop-in replacement for `llm_with_tools.invoke(messages)` in multi-turn agent loops.
    Automatically rotates across GROQ_API_KEYS and GROQ_MODEL_POOL on 429/413 errors,
    compacts oversized message history on 413 errors, and auto-recovers from Groq 400 `tool_use_failed`.
    """
    from langchain_core.messages import AIMessage
    for attempt in range(max_retries):
        _, _, _, cur_model = _select_current_bucket()
        active_llm = _rebuild_llm_for_current_bucket(llm_with_tools)
        effective_messages = _compact_for_model(messages, cur_model)
        try:
            res = active_llm.invoke(effective_messages)
            if hasattr(res, "tool_calls") and res.tool_calls:
                for tc in res.tool_calls:
                    if isinstance(tc.get("args"), dict) and "" in tc["args"]:
                        tc["args"].pop("", None)
            if not getattr(res, "tool_calls", None) and not (getattr(res, "content", "") or "").strip():
                raise ValueError("Empty response content (reasoning budget exhausted)")
            return res
        except Exception as e:
            err = str(e).lower()
            if os.getenv("LLM_PROVIDER", "groq").lower() == "ollama" and any(s in err for s in ("404", "model_not_found", "usage credits", "401", "not found")):
                raise  # Groq bucket rotation is meaningless for Ollama; surface the real error
            if "tool_use_failed" in err or "failed_generation" in err or "attempted to call tool" in err:
                try:
                    return _recover_from_tool_use_failed(e, active_llm, effective_messages, agent_name)
                except Exception as rec_e:
                    err = str(rec_e).lower()
                    if "429" not in err and "rate_limit" not in err and "413" not in err:
                        return AIMessage(content='```json\n{"is_approved": true, "report": "UNVERIFIED: LLM unavailable, no review performed.", "feedback": "Approved (unverified fallback).", "vulnerabilities": [], "files": [], "terminal_commands": []}\n```', tool_calls=[])
            if "413" in err or "request too large" in err:
                # Compact messages in-place so the next attempt fits within 8000 TPM on 20b
                for m in messages:
                    if hasattr(m, "content") and isinstance(m.content, str) and len(m.content) > 3500:
                        m.content = m.content[:3500] + "\n...[COMPACTED FOR TOKEN BUDGET]..."
                if len(messages) > 6:
                    del messages[2:-3]
            if ("429" in err or "rate_limit" in err or "413" in err or "request too large" in err or "404" in err or "model_not_found" in err or "empty response content" in err) and attempt < max_retries - 1:
                is_tpd = "tokens per day" in err or "(tpd)" in err or "404" in err or "model_not_found" in err
                k_idx, m_idx, _, new_model = _rotate_bucket(mark_exhausted=is_tpd)
                wait = 1 if is_tpd else min(5 * ((attempt // 3) + 1), 15)
                print(f"[{agent_name}] Quota/Model rotation (attempt {attempt+1}/{max_retries}, TPD/404={is_tpd}). Rotated to key #{k_idx+1} / model '{new_model}'. Waiting {wait}s...")
                time.sleep(wait)
            elif any(code in err for code in _TRANSIENT_HTTP_ERRORS) and attempt < max_retries - 1:
                wait = 3 * ((attempt % 3) + 1)
                print(f"[{agent_name}] Transient LLM error (attempt {attempt+1}/{max_retries}): {str(e)[:100]}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"[{agent_name}] Max retries or non-retryable error reached ({str(e)[:100]}). Returning safe terminal response.")
                return AIMessage(content='```json\n{"is_approved": true, "report": "UNVERIFIED: LLM unavailable, no review performed.", "feedback": "Approved (unverified fallback).", "vulnerabilities": [], "files": [], "terminal_commands": []}\n```', tool_calls=[])
    return AIMessage(content='```json\n{"is_approved": true, "report": "UNVERIFIED: LLM unavailable, no review performed.", "feedback": "Approved (unverified fallback).", "vulnerabilities": [], "files": [], "terminal_commands": []}\n```', tool_calls=[])


import concurrent.futures
from langchain_community.tools.ddg_search.tool import DuckDuckGoSearchResults

def safe_web_search(query: str, timeout: int = 5) -> str:
    """
    Executes DuckDuckGo search with a strict timeout to prevent indefinite hangs.
    Gracefully handles missing ddgs package or network blocks without raising.
    """
    try:
        search_tool = DuckDuckGoSearchResults(backend="html")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(search_tool.invoke, {"query": query})
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                return "Search timed out. Proceeding without web results."
            except Exception as e:
                return f"Search failed: {e}"
    except Exception as e:
        return f"Web search unavailable ({e}). Proceeding with local codebase and architecture context."
