"""
Stack-aware project build/compile verifier.

Runs the real compiler / typechecker / syntax checker for whatever stack is
present in the active project workspace (Maven, Gradle, Node/TypeScript/npm build,
Python py_compile, Go, Rust, .NET) using ``run_command_safe`` so it never hangs.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

from agents.src.shared.proc import run_command_safe
from agents.src.shared.workspace import get_output_dir

_SKIP_DIRS = {"node_modules", ".git", "target", "build", "dist", ".next", "__pycache__", ".venv", "venv"}


def _iter_files(root: Path, suffixes: set[str]) -> list[Path]:
    found: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in suffixes:
            continue
        try:
            rel_parts = p.relative_to(root).parts
        except ValueError:
            continue
        if _SKIP_DIRS.intersection(rel_parts):
            continue
        found.append(p)
    return found


def verify_project_build(output_dir: Optional[Path] = None, label: str = "BuildVerify") -> Tuple[bool, str]:
    """
    Detects the project stack(s) in ``output_dir`` and runs a real compile/build check.
    Returns ``(passed, error_output)``.
    """
    root = output_dir or get_output_dir()
    if not root.exists():
        return True, ""

    errors: list[str] = []

    # 1. Java — Maven
    if (root / "pom.xml").exists():
        rc, out, err, timed_out = run_command_safe("mvn -B -q compile", root, timeout=120)
        if timed_out:
            errors.append("[Maven] `mvn -B -q compile` timed out after 120s.")
        elif rc != 0:
            errors.append(f"[Maven compile failed]\n{(out + err)[-2000:]}")
        else:
            print(f"[{label}] Maven compile: PASSED")

    # 2. Java — Gradle
    elif (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        cmd = "gradlew.bat compileJava" if (os.name == "nt" and (root / "gradlew.bat").exists()) else "gradle compileJava"
        rc, out, err, timed_out = run_command_safe(cmd, root, timeout=120)
        if timed_out:
            errors.append(f"[Gradle] `{cmd}` timed out after 120s.")
        elif rc != 0:
            errors.append(f"[Gradle compile failed]\n{(out + err)[-2000:]}")
        else:
            print(f"[{label}] Gradle compile: PASSED")

    # 3. Node / TypeScript / JS (root or nested frontend/backend package.json)
    pkg_candidates = [root / "package.json", root / "frontend" / "package.json", root / "backend" / "package.json"]
    checked_node_dirs: set[Path] = set()
    for pkg in pkg_candidates:
        if not pkg.exists():
            continue
        pkg_dir = pkg.parent
        checked_node_dirs.add(pkg_dir)
        has_node_modules = (pkg_dir / "node_modules").exists()
        try:
            pkg_json = json.loads(pkg.read_text(encoding="utf-8"))
        except Exception:
            pkg_json = {}
        scripts = pkg_json.get("scripts") or {}

        # TypeScript check if tsconfig.json exists and tsc is installed locally
        if (pkg_dir / "tsconfig.json").exists() and has_node_modules:
            rc, out, err, timed_out = run_command_safe("npx --no-install tsc --noEmit --skipLibCheck", pkg_dir, timeout=90)
            combined = out + err
            if timed_out:
                errors.append(f"[TypeScript in {pkg_dir.name}] `tsc --noEmit` timed out.")
            elif rc != 0 and "TS18003" not in combined:
                errors.append(f"[TypeScript check failed in {pkg_dir.name}]\n{combined[-2000:]}")
            else:
                print(f"[{label}] TypeScript ({pkg_dir.name}): PASSED")

        # Run build script if dependencies are installed
        if scripts.get("build") and has_node_modules:
            rc, out, err, timed_out = run_command_safe("npm run build", pkg_dir, timeout=180)
            if timed_out:
                errors.append(f"[npm build in {pkg_dir.name}] timed out after 180s.")
            elif rc != 0:
                errors.append(f"[npm run build failed in {pkg_dir.name}]\n{(out + err)[-2000:]}")
            else:
                print(f"[{label}] npm run build ({pkg_dir.name}): PASSED")

    # Plain JS syntax check if .js files exist without a build/tsc pass
    if not checked_node_dirs:
        js_files = _iter_files(root, {".js", ".mjs", ".cjs"})
        for jf in js_files[:30]:
            rc, out, err, _ = run_command_safe(f'node --check "{jf}"', root, timeout=15)
            if rc != 0:
                errors.append(f"[JS syntax error in {jf.relative_to(root)}]\n{(out + err)[-1000:]}")

    # 4. Python syntax check (py_compile)
    py_files = _iter_files(root, {".py"})
    if py_files:
        quoted = " ".join(f'"{p}"' for p in py_files[:50])
        rc, out, err, timed_out = run_command_safe(f'"{sys.executable}" -m py_compile {quoted}', root, timeout=60)
        if timed_out:
            errors.append("[Python] py_compile timed out.")
        elif rc != 0:
            errors.append(f"[Python syntax check failed]\n{(out + err)[-2000:]}")
        else:
            print(f"[{label}] Python py_compile ({len(py_files)} files): PASSED")

    # 5. Go
    if (root / "go.mod").exists():
        rc, out, err, timed_out = run_command_safe("go build ./...", root, timeout=120)
        if timed_out:
            errors.append("[Go] `go build ./...` timed out.")
        elif rc != 0:
            errors.append(f"[Go build failed]\n{(out + err)[-2000:]}")
        else:
            print(f"[{label}] Go build: PASSED")

    # 6. Rust
    if (root / "Cargo.toml").exists():
        rc, out, err, timed_out = run_command_safe("cargo check", root, timeout=180)
        if timed_out:
            errors.append("[Rust] `cargo check` timed out.")
        elif rc != 0:
            errors.append(f"[Rust cargo check failed]\n{(out + err)[-2000:]}")
        else:
            print(f"[{label}] Rust cargo check: PASSED")

    # 7. .NET / C#
    if list(root.glob("*.csproj")):
        rc, out, err, timed_out = run_command_safe("dotnet build --nologo", root, timeout=180)
        if timed_out:
            errors.append("[.NET] `dotnet build` timed out.")
        elif rc != 0:
            errors.append(f"[.NET build failed]\n{(out + err)[-2000:]}")
        else:
            print(f"[{label}] .NET build: PASSED")

    if errors:
        return False, "\n\n".join(errors)[:3000]
    return True, ""
