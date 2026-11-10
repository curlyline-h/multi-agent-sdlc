"""
End-to-End Requirement & Import Completeness Verifier for Backend and Frontend Agents.

Ensures that after an agent's multi-turn tool loop:
1. Placeholder files (`src/file.ts`, `src/file.tsx`, content == `"raw code"`) are purged.
2. Every assigned task / PRD requirement has concrete route/service (Backend) or page/component (Frontend) files.
3. Every local relative import (`import ... from "./..."`) across `src/` resolves to an actual file on disk.
4. Every route module in `src/routes/` is mounted in `src/app.ts` / `src/index.ts`.
"""
import json
import re
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage
from agents.src.shared.llm import get_llm, llm_invoke_with_retry


def _strip_code_fences(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"```(?:typescript|ts|tsx|javascript|js|jsx|python|py|json|html|css)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Handle case where opening fence is present without closing fence
    cleaned = re.sub(r"^```(?:typescript|ts|tsx|javascript|js|jsx|python|py|json|html|css)?\s*\n", "", text.strip())
    cleaned = re.sub(r"\n```\s*$", "", cleaned)
    return cleaned.strip()


def _finalize_ts_code(code: str, is_router: bool = False, default_export_name: str = "") -> str:
    """
    Ensures generated TypeScript/React code is never left truncated mid-statement if max_tokens is reached.
    If `export default` is missing, trims any trailing incomplete block back to the last complete `});` or `};`
    and appends a valid JSX return (if inside an unclosed component) and `export default`.
    """
    code = _strip_code_fences(code)
    if not code:
        return ""
    if "export default" in code:
        return code
    if is_router:
        last_close = code.rfind("});")
        if last_close != -1:
            code = code[: last_close + 3] + "\n\nexport default router;\n"
        else:
            code = code + "\nexport default router;\n"
        return code
    # For non-router TS/TSX modules
    last_semi = max(code.rfind("};"), code.rfind("});"))
    if last_semi != -1:
        sep_len = 3 if code[last_semi : last_semi + 3] == "});" else 2
        code = code[: last_semi + sep_len]
    # Balance any remaining open braces (e.g. if a React component body was open when truncated)
    open_braces = code.count("{") - code.count("}")
    if open_braces > 0 and default_export_name:
        if "return (" not in code and "return <" not in code:
            code += (
                f"\n\n  return (\n"
                f'    <div className="p-6 max-w-5xl mx-auto">\n'
                f'      <h1 className="text-2xl font-bold mb-4">{default_export_name}</h1>\n'
                f"    </div>\n"
                f"  );\n"
            )
        code += "\n" + ("};\n" * open_braces)
    if default_export_name and f"export default {default_export_name}" not in code:
        code = code.rstrip() + f"\n\nexport default {default_export_name};\n"
    return code


def purge_placeholder_files(output_dir: Path) -> list[str]:
    """Removes bogus placeholder files like src/file.ts, src/file.tsx, truncated fence files, or files containing 'raw code'."""
    removed = []
    src_dir = output_dir / "src"
    if not src_dir.exists():
        return removed
    for p in list(src_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(output_dir)).replace("\\", "/")
        try:
            content = p.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
        is_truncated_fence = content.startswith("```")
        if p.name in ("file.ts", "file.tsx", "file.js", "file.py") or content in ("raw code", "...", "") or is_truncated_fence:
            try:
                p.unlink()
                removed.append(rel)
                print(f"[CodeCompleteness] Purged placeholder/truncated file: {rel}")
            except Exception:
                pass
        elif p.suffix in (".ts", ".tsx") and ("export " not in content or (p.suffix == ".tsx" and "export default" not in content)):
            fixed = _finalize_ts_code(content, is_router=("/routes/" in rel), default_export_name=p.stem[:1].upper() + p.stem[1:])
            p.write_text(fixed + "\n", encoding="utf-8")
            print(f"[CodeCompleteness] Auto-finalized missing export in: {rel}")
    return removed


def find_missing_local_imports(output_dir: Path) -> list[tuple[Path, str, Path]]:
    """
    Scans all .ts/.tsx/.js/.jsx files under output_dir/src for relative imports
    (`from './...'` or `from '../...'`) and returns a list of
    (importer_path, import_specifier, target_path_to_create) for any missing module.
    """
    src_dir = output_dir / "src"
    if not src_dir.exists():
        return []

    import_pattern = re.compile(
        r"""(?:import\s+(?:type\s+)?(?:[\w*\s{},]+?\s+from\s+)?|export\s+[\w*\s{},]+?\s+from\s+|require\s*\(\s*)['"](\.\.?/[^'"]+)['"]"""
    )
    extensions = [".ts", ".tsx", ".js", ".jsx", ".json", ".css"]
    missing: list[tuple[Path, str, Path]] = []
    seen_targets: set[str] = set()

    for src_file in sorted(src_dir.rglob("*")):
        if not src_file.is_file() or src_file.suffix not in (".ts", ".tsx", ".js", ".jsx"):
            continue
        try:
            content = src_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for match in import_pattern.finditer(content):
            spec = match.group(1).strip()
            # Reject degenerate hallucinated imports like PostTypeType / PostTypeTypeType
            if re.search(r"(Type){2,}|(\w{3,}?)\2{2,}", spec.split("/")[-1]):
                continue
            base_target = (src_file.parent / spec).resolve()
            # Check if file exists directly or with standard extensions or index file
            exists = False
            if base_target.is_file():
                exists = True
            else:
                for ext in extensions:
                    if base_target.with_suffix(ext).is_file():
                        exists = True
                        break
                    if (base_target / f"index{ext}").is_file():
                        exists = True
                        break
            if not exists:
                # Decide extension based on importer or path
                _backend_dirs = ("/controllers/", "/services/", "/models/", "/routes/", "/middlewares/",
                                 "/middleware/", "/repositories/", "/utils/", "/db/", "/config/", "/types/")
                _spec_norm = "/" + spec.replace("\\", "/").lstrip("./")
                _is_backend_spec = any(d in _spec_norm for d in _backend_dirs) or any(
                    d in "/" + str(src_file.relative_to(src_dir)).replace("\\", "/") for d in _backend_dirs
                )
                is_react = (not _is_backend_spec) and (
                    "/pages/" in spec
                    or "/components/" in spec
                    or "/hooks/" in spec
                    or (src_file.suffix in (".tsx", ".jsx") and spec.split("/")[-1][:1].isupper())
                )
                default_ext = ".tsx" if is_react else ".ts"
                if base_target.suffix in extensions:
                    target_path = base_target
                else:
                    target_path = base_target.with_suffix(default_ext)
                key = str(target_path)
                if key not in seen_targets:
                    seen_targets.add(key)
                    missing.append((src_file, spec, target_path))
    return missing


def _broadcast_created_file(output_dir: Path, file_path: Path):
    try:
        from backend.telemetry import broadcast_tool_call
        rel_p = str(file_path.relative_to(output_dir)).replace("\\", "/")
        broadcast_tool_call(
            "create_file",
            rel_p,
            event_type="FILE_CHANGE",
            payload_extra={"path": rel_p, "action": "CREATED", "diff": f"+ Created file {rel_p}"},
        )
    except Exception:
        pass


def resolve_missing_local_imports(output_dir: Path, design_doc: str, db_schema: str, role: str = "backend") -> list[str]:
    """
    Iteratively resolves missing local relative imports in `output_dir/src` by generating
    each missing module with full context of the importing file, DB schema, and design doc.
    """
    created_files: list[str] = []
    llm = get_llm(temperature=0.1, max_tokens=1600)

    for _pass in range(2):
        missing = find_missing_local_imports(output_dir)
        if not missing:
            break
        for importer_path, spec, target_path in missing[:10]:
            try:
                rel_target = str(target_path.relative_to(output_dir)).replace("\\", "/")
                rel_importer = str(importer_path.relative_to(output_dir)).replace("\\", "/")
                importer_code = importer_path.read_text(encoding="utf-8", errors="replace")[:2500]
            except Exception:
                continue

            # Gather existing routes/types context so frontend pages call real backend endpoints
            routes_summary = ""
            routes_dir = output_dir / "src" / "routes"
            if routes_dir.exists():
                for rf in sorted(routes_dir.glob("*.ts"))[:6]:
                    try:
                        routes_summary += f"\n// File: src/routes/{rf.name}\n" + rf.read_text(encoding="utf-8", errors="replace")[:900]
                    except Exception:
                        pass

            prompt = [
                SystemMessage(content=(
                    f"You are a Senior {role.capitalize()} Engineer. Output ONLY the raw TypeScript/React source code "
                    f"for `{rel_target}` wrapped in a single ```tsx or ```ts code block. "
                    f"Keep the implementation concise and complete (under 90 lines) so it never truncates, "
                    f"and MUST end with `export default`. Implement all functions/components imported by `{rel_importer}`."
                )),
                HumanMessage(content=(
                    f"The file `{rel_importer}` imports `{spec}` (which resolves to `{rel_target}`), "
                    f"but `{rel_target}` does not exist yet.\n\n"
                    f"=== Importing File (`{rel_importer}`) ===\n{importer_code}\n\n"
                    f"=== Existing Backend Routes ===\n{routes_summary[:2000]}\n\n"
                    f"=== Database Schema (`db/init.sql`) ===\n{(db_schema or '')[:1500]}\n\n"
                    f"=== System Design Summary ===\n{(design_doc or '')[:1500]}\n\n"
                    f"Write the complete, production-ready code for `{rel_target}` now."
                )),
            ]
            try:
                resp = llm_invoke_with_retry(llm, prompt)
                stem_export = re.sub(r"[^a-zA-Z0-9_]", "", target_path.stem[:1].upper() + target_path.stem[1:])
                code = _finalize_ts_code(
                    getattr(resp, "content", ""),
                    is_router=("/routes/" in rel_target),
                    default_export_name=(stem_export if target_path.suffix == ".tsx" else ""),
                )
            except Exception as e:
                print(f"[CodeCompleteness] LLM fallback synthesis for missing import {rel_target}: {e}")
                code = _synthesize_fallback_module(target_path, importer_code)

            if code and len(code.strip()) > 20:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(code + "\n", encoding="utf-8")
                created_files.append(rel_target)
                print(f"[CodeCompleteness] Resolved missing import -> wrote {rel_target}")
                _broadcast_created_file(output_dir, target_path)

    return created_files


def _synthesize_fallback_module(target_path: Path, importer_code: str) -> str:
    """Deterministic TypeScript/React fallback module if all LLM buckets are unreachable."""
    stem = target_path.stem
    comp_name = re.sub(r"[^a-zA-Z0-9_]", "", stem[:1].upper() + stem[1:]) or "ModuleComponent"
    if target_path.suffix == ".tsx":
        return (
            f'import React, {{ useState, useEffect }} from "react";\n\n'
            f"export const {comp_name}: React.FC = () => {{\n"
            f"  const [items, setItems] = useState<any[]>([]);\n"
            f"  const [loading, setLoading] = useState<boolean>(false);\n"
            f"  const [error, setError] = useState<string | null>(null);\n\n"
            f"  useEffect(() => {{\n"
            f"    setLoading(false);\n"
            f"  }}, []);\n\n"
            f"  return (\n"
            f'    <div className="p-6 max-w-6xl mx-auto">\n'
            f'      <h1 className="text-2xl font-bold mb-4">{stem}</h1>\n'
            f'      {{error && <div className="text-red-600 mb-3">{{error}}</div>}}\n'
            f'      {{loading ? <p>Loading...</p> : <div className="grid gap-4">{{items.length === 0 ? <p>Ready.</p> : null}}</div>}}\n'
            f"    </div>\n"
            f"  );\n"
            f"}};\n\n"
            f"export default {comp_name};\n"
        )
    return f"// {target_path.name}\nexport default {{}};\n"


def ensure_backend_tasks_and_routes_wired(
    output_dir: Path,
    tasks_str: str,
    design_doc: str,
    db_schema: str,
) -> list[str]:
    """
    1. Checks `db/init.sql` tables and `tasks_str` to see if any core domain entity is missing a route in `src/routes/`.
    2. Generates missing route modules (e.g. `src/routes/menu.ts` when `menu_items`/`allergens` tables exist in `db/init.sql`).
    3. Ensures `src/app.ts` mounts EVERY router in `src/routes/*.ts` and exposes `/health`.
    """
    created_or_updated: list[str] = []
    purge_placeholder_files(output_dir)

    # The wiring below generates TypeScript/Express modules; only do so for Node/TS projects.
    if detect_project_stack(design_doc, output_dir)["language"] not in ("node", "unknown"):
        print("[CodeCompleteness] Non-Node backend detected; skipping TS/Express route wiring.")
        return created_or_updated

    # Parse SQL tables from db/init.sql
    sql_path = output_dir / "db" / "init.sql"
    sql_text = sql_path.read_text(encoding="utf-8", errors="replace") if sql_path.exists() else (db_schema or "")
    tables = re.findall(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)", sql_text, re.IGNORECASE)
    tables = [t.lower() for t in tables if t.lower() not in ("schema_migrations", "migrations")]

    routes_dir = output_dir / "src" / "routes"
    routes_dir.mkdir(parents=True, exist_ok=True)
    existing_routes = {p.stem.lower(): p for p in routes_dir.glob("*.ts")}

    llm = get_llm(temperature=0.1, max_tokens=1600)

    # Identify domain tables not yet covered by any route file
    existing_routes_concat = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in existing_routes.values()
    ).lower()

    uncovered_tables = []
    for tbl in tables:
        singular = tbl.rstrip("s")
        if tbl not in existing_routes_concat and singular not in existing_routes_concat and tbl not in existing_routes:
            uncovered_tables.append(tbl)

    # Also if there are NO routes at all yet, ensure at least core domain routes are generated
    if not existing_routes and tables:
        uncovered_tables = tables[:4]

    if uncovered_tables:
        # Group uncovered tables into up to 2 cohesive route modules so we don't spam files
        module_name = uncovered_tables[0].replace("_items", "").replace("_records", "")
        if module_name in existing_routes:
            module_name = f"{module_name}_domain"
        target_route_file = routes_dir / f"{module_name}.ts"
        rel_route = f"src/routes/{module_name}.ts"

        prompt = [
            SystemMessage(content=(
                "You are a Senior Backend TypeScript/Express Engineer. Output ONLY the raw TypeScript code "
                f"for `{rel_route}` wrapped in a ```ts code block. Keep the file concise and complete (under 95 lines) "
                "implementing full CRUD / filter REST endpoints for the specified database tables, ending with `export default router;`."
            )),
            HumanMessage(content=(
                f"Generate `{rel_route}` implementing Express REST endpoints for database tables: {uncovered_tables}.\n\n"
                f"=== Assigned Backend Tasks ===\n{tasks_str[:1800]}\n\n"
                f"=== Database Schema (`db/init.sql`) ===\n{sql_text[:2000]}\n\n"
                f"=== System Design ===\n{(design_doc or '')[:1500]}\n\n"
                f"Export default router."
            )),
        ]
        try:
            resp = llm_invoke_with_retry(llm, prompt)
            code = _finalize_ts_code(getattr(resp, "content", ""), is_router=True)
            if code and "Router" in code and len(code) > 60:
                target_route_file.write_text(code + "\n", encoding="utf-8")
                created_or_updated.append(rel_route)
                print(f"[CodeCompleteness] Generated missing domain route module: {rel_route} (tables: {uncovered_tables})")
                _broadcast_created_file(output_dir, target_route_file)
        except Exception as e:
            print(f"[CodeCompleteness] Could not generate domain route {rel_route}: {e}")

    # Resolve any missing local imports across backend src/
    resolved_imports = resolve_missing_local_imports(output_dir, design_doc, sql_text, role="backend")
    created_or_updated.extend(resolved_imports)

    # Ensure src/app.ts mounts ALL route files in src/routes/*.ts and exposes /health
    all_route_files = sorted(routes_dir.glob("*.ts"))
    app_file = output_dir / "src" / "app.ts"
    if all_route_files:
        app_content = app_file.read_text(encoding="utf-8", errors="replace") if app_file.exists() else ""
        unmounted = [rf for rf in all_route_files if f"./routes/{rf.stem}" not in app_content and f"routes/{rf.stem}" not in app_content]
        if not app_file.exists() or unmounted or "/health" not in app_content:
            imports_block = [
                'import express, { Request, Response } from "express";',
                'import dotenv from "dotenv";',
            ]
            mounts_block = []
            for rf in all_route_files:
                var_name = re.sub(r"[^a-zA-Z0-9_]", "_", rf.stem) + "Router"
                imports_block.append(f'import {var_name} from "./routes/{rf.stem}";')
                mounts_block.append(f'app.use("/api/v1/{rf.stem.replace("_", "-")}", {var_name});')

            new_app_ts = (
                "// src/app.ts\n"
                + "\n".join(imports_block)
                + "\n\ndotenv.config();\n"
                + "export const app = express();\n"
                + "app.use(express.json());\n\n"
                + 'app.get("/health", (_req: Request, res: Response) => {\n'
                + '  res.status(200).json({ status: "ok", service: "backend-api" });\n'
                + "});\n\n"
                + "// Mounted Domain Routers\n"
                + "\n".join(mounts_block)
                + "\n\nconst port = process.env.PORT || 3000;\n"
                + 'if (process.env.NODE_ENV !== "test") {\n'
                + "  app.listen(port, () => {\n"
                + "    console.log(`Server running on port ${port}`);\n"
                + "  });\n"
                + "}\n\nexport default app;\n"
            )
            app_file.parent.mkdir(parents=True, exist_ok=True)
            app_file.write_text(new_app_ts, encoding="utf-8")
            created_or_updated.append("src/app.ts")
            print(f"[CodeCompleteness] Wired all {len(all_route_files)} route module(s) + /health in src/app.ts")
            _broadcast_created_file(output_dir, app_file)

    return created_or_updated


def ensure_frontend_completeness(
    output_dir: Path,
    tasks_str: str,
    design_doc: str,
    db_schema: str,
) -> list[str]:
    """
    1. Purges any placeholder files (`src/file.tsx`).
    2. If `src/App.tsx` does not exist yet, generates a cohesive `src/App.tsx` + domain pages for the scenario.
    3. Recursively resolves all missing local imports (`./pages/...`, `./components/...`, `./store/...`, `./utils/...`)
       so every imported page and component in `src/App.tsx` exists and is fully implemented.
    """
    created_or_updated: list[str] = []
    purge_placeholder_files(output_dir)

    if not detect_project_stack(design_doc, output_dir)["frontend_react"]:
        print("[CodeCompleteness] Non-React frontend detected; skipping React/TSX completeness pass.")
        return created_or_updated

    src_dir = output_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    app_tsx = src_dir / "App.tsx"

    llm = get_llm(temperature=0.1, max_tokens=1600)

    if not app_tsx.exists():
        routes_summary = ""
        routes_dir = src_dir / "routes"
        if routes_dir.exists():
            for rf in sorted(routes_dir.glob("*.ts"))[:6]:
                try:
                    routes_summary += f"\n// src/routes/{rf.name}\n" + rf.read_text(encoding="utf-8", errors="replace")[:800]
                except Exception:
                    pass

        prompt = [
            SystemMessage(content=(
                "You are a Senior React/TypeScript Frontend Architect. Output ONLY the raw TypeScript React code "
                "for `src/App.tsx` wrapped in a ```tsx code block. Keep the file concise (under 65 lines total) "
                "with inline types and a complete JSX return ending with `export default App;`. Do NOT import external CSS files."
            )),
            HumanMessage(content=(
                f"=== Assigned Frontend Tasks ===\n{tasks_str[:1800]}\n\n"
                f"=== Backend API Routes ===\n{routes_summary[:1800]}\n\n"
                f"=== System Design ===\n{(design_doc or '')[:1500]}\n\n"
                "Write `src/App.tsx` now."
            )),
        ]
        try:
            resp = llm_invoke_with_retry(llm, prompt)
            code = _finalize_ts_code(getattr(resp, "content", ""), is_router=False, default_export_name="App")
            if code and len(code) > 50:
                app_tsx.write_text(code + "\n", encoding="utf-8")
                created_or_updated.append("src/App.tsx")
                print("[CodeCompleteness] Generated missing src/App.tsx")
                _broadcast_created_file(output_dir, app_tsx)
        except Exception as e:
            print(f"[CodeCompleteness] Could not generate src/App.tsx: {e}")

    resolved = resolve_missing_local_imports(output_dir, design_doc, db_schema, role="frontend")
    created_or_updated.extend(resolved)
    return created_or_updated



_TOOL_NAMES = {
    "list_directory", "search_web", "read_file_range", "semantic_code_search", "db_schema_inspector",
    "fetch_server_logs", "replace_file_content", "write_file", "rag_search", "code_linter",
    "run_unit_tests", "run_terminal_command", "create_project_database", "run_migrations",
    "validate_schema_diff",
}


def filter_terminal_commands(cmds) -> list[str]:
    """Drops LangChain tool names / non-commands that models mistakenly put into terminal_commands."""
    out = []
    for c in cmds or []:
        c = str(c).strip()
        if not c or c in _TOOL_NAMES or c.split("(")[0].strip() in _TOOL_NAMES:
            print(f"[CodeCompleteness] Dropped tool name from terminal_commands: {c!r}")
            continue
        out.append(c)
    return out


_SUMMARY_SKIP_DIRS = {"docs", "node_modules", ".git", ".next", "dist", "build", "coverage", "target", "vendor", "__pycache__", ".venv", "venv"}
_SUMMARY_SKIP_FILES = {"package-lock.json", "issue_board.json", "jira_tickets.json", "tasks-proj.json",
                       "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock"}


def prioritized_code_paths(output_dir: Path) -> list[Path]:
    """Ordered code files for context summaries: db/ first, then src/, then the rest.
    Excludes docs, lockfiles and tracker json so src/ is never starved of context budget."""
    files = []
    for p in output_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(output_dir)
        if any(part in _SUMMARY_SKIP_DIRS for part in rel.parts) or p.name in _SUMMARY_SKIP_FILES:
            continue
        if p.suffix == ".json" and p.name not in ("package.json", "tsconfig.json", "composer.json"):
            continue
        files.append(p)

    def key(p: Path):
        top = p.relative_to(output_dir).parts[0]
        return (0 if top == "db" else 1 if top == "src" else 2, str(p))

    return sorted(files, key=key)



# ---------------------------------------------------------------------------
# Technology-agnostic stack detection / contract
# ---------------------------------------------------------------------------
_STACK_KEYWORDS = {
    "python": r"fastapi|django|flask|python|pydantic|sqlalchemy|uvicorn",
    "node": r"express|nestjs|node\.?js|typescript|fastify|koa|npm|prisma",
    "go": r"golang|\bgin\b|go\.mod|\bgorm\b|go module",
    "java": r"spring|java\b|kotlin|maven|gradle|hibernate",
    "ruby": r"rails|ruby|sinatra",
    "php": r"laravel|php|symfony",
    "dotnet": r"asp\.net|c#|\.net core|entity framework",
    "rust": r"actix|axum|\brust\b|cargo",
}
_STACK_FILES = {
    "node": ("package.json",), "python": ("requirements.txt", "pyproject.toml", "setup.py"),
    "java": ("pom.xml", "build.gradle", "build.gradle.kts"), "go": ("go.mod",), "rust": ("Cargo.toml",),
    "ruby": ("Gemfile",), "php": ("composer.json",),
}


def detect_project_stack(design_doc: str, output_dir: Path) -> dict:
    """Detects the backend language from files already on disk, else from the design doc.
    Returns {"language": str|"unknown", "frontend_react": bool}."""
    language = "unknown"
    for lang, names in _STACK_FILES.items():
        if any((output_dir / n).exists() for n in names):
            language = lang
            break
    text = (design_doc or "").lower()
    if language == "unknown" and text:
        scores = {k: len(re.findall(rx, text)) for k, rx in _STACK_KEYWORDS.items()}
        best = max(scores, key=scores.get)
        if scores[best] > 0:
            language = best
    other_fe = re.search(r"\b(vue|angular|svelte|solid\.?js|htmx)\b", text)
    mentions_react = bool(re.search(r"\breact\b|next\.?js|\.tsx", text))
    has_tsx = (output_dir / "src" / "App.tsx").exists()
    frontend_react = mentions_react or has_tsx or not other_fe
    return {"language": language, "frontend_react": frontend_react}


def stack_contract_text(role: str, design_doc: str, output_dir: Path = None) -> str:
    """Prompt text forcing every task to follow the technology demanded by the requirements.
    Persists the first decision in docs/STACK.md so later tasks stay consistent."""
    if output_dir is None:
        from agents.src.shared.tools import get_output_dir
        output_dir = get_output_dir()
    info = detect_project_stack(design_doc, output_dir)
    stack_md = output_dir / "docs" / "STACK.md"
    recorded = ""
    try:
        if stack_md.exists():
            recorded = stack_md.read_text(encoding="utf-8", errors="replace")[:1500]
        elif info["language"] != "unknown":
            stack_md.parent.mkdir(parents=True, exist_ok=True)
            stack_md.write_text(
                f"# Project Stack Contract\n\nDetected backend language/runtime: {info['language']}\n"
                "All tasks must use the frameworks, ORM/DB driver and conventions named in the System Design.\n",
                encoding="utf-8",
            )
            recorded = stack_md.read_text(encoding="utf-8")
    except Exception:
        pass
    return (
        f"Technology rule ({role}): implement with EXACTLY the languages, frameworks, database and libraries that the "
        "user requirements, PRD and System Design specify - whatever they are. "
        f"Detected from the project/design: {info['language']}. "
        "If none is specified, choose the most standard fit, write the decision to docs/STACK.md, and every later task "
        "must follow it. Use file extensions, folder layout and idioms of that stack. "
        "Use ONE library per concern (one web framework, one ORM/DB driver); never mix competing ones across files. "
        "Read the existing code above and stay consistent with it. Implement ONLY the entities, endpoints and screens "
        "in the PRD / db schema; never add unrelated generic entities.\n"
        + (f"Recorded stack contract (docs/STACK.md):\n{recorded}\n" if recorded else "")
    )
