"""
Safe subprocess runner for agent tools.

Problems this solves (all observed with ``subprocess.run(shell=True, timeout=...)``):
  * On Windows, a timeout only kills ``cmd.exe`` - child processes (npx/node/mvn/java)
    keep the stdout/stderr pipes open, so the follow-up ``communicate()`` blocks forever.
  * Child tools such as ``npx`` can wait for interactive input ("Ok to proceed? (y)").

``run_command_safe`` always closes stdin, runs the command in its own process group,
and on timeout kills the WHOLE process tree before returning.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple, Union


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=15, check=False,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


_PYTHON_CMD_PREFIXES = ("pip ", "pip3 ", "python ", "python3 ", "pytest", "uvicorn", "alembic", "ruff ")


def _resolve_project_root(cwd_path: Path) -> Optional[Path]:
    """If cwd_path is inside projects/<slug>/..., return that project's root directory."""
    parts = cwd_path.resolve().parts
    if "projects" in parts:
        idx = parts.index("projects")
        if idx + 1 < len(parts):
            return Path(*parts[: idx + 2])
    return None


def _ensure_isolated_venv(command: str, cwd_path: Path, env: dict) -> None:
    """
    When running Python/pip/pytest inside a generated project workspace, ensure
    it uses an isolated `<project>/.venv` rather than the platform's Poetry venv.
    """
    cmd_lower = command.strip().lower()
    if not any(cmd_lower.startswith(p) or f" {p}" in cmd_lower for p in _PYTHON_CMD_PREFIXES):
        return
    proj_root = _resolve_project_root(cwd_path)
    if not proj_root:
        return

    venv_dir = proj_root / ".venv"
    bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    py_exe = bin_dir / ("python.exe" if os.name == "nt" else "python")
    if not py_exe.exists():
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                capture_output=True,
                timeout=60,
                check=False,
            )
        except Exception:
            return

    if bin_dir.exists():
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        env["VIRTUAL_ENV"] = str(venv_dir)
        env.pop("POETRY_ACTIVE", None)


def run_command_safe(
    command: str,
    cwd: Union[str, Path],
    timeout: int = 120,
    extra_env: Optional[dict] = None,
) -> Tuple[int, str, str, bool]:
    """
    Runs ``command`` and returns ``(returncode, stdout, stderr, timed_out)``.
    Never blocks longer than ``timeout`` (+ a few seconds of cleanup).
    """
    env = {**os.environ, "CI": "1"}
    if extra_env:
        env.update(extra_env)
    _ensure_isolated_venv(command, Path(cwd), env)

    kwargs: dict = dict(
        shell=True,
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(command, **kwargs)
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out or "", err or "", False
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=10)
        except Exception:
            out, err = "", ""
        return -1, out or "", err or "", True
