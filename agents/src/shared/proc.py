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
