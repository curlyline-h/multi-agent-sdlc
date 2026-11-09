import os
import subprocess
from typing import List, Dict, Any, Optional

class GitService:
    @staticmethod
    def get_git_diff(repo_path: str = ".") -> str:
        """Returns the unified git diff for unstaged and staged changes in repo_path."""
        try:
            res = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10
            )
            if res.returncode == 0:
                return res.stdout
            # Fallback to unstaged diff
            res_unstaged = subprocess.run(
                ["git", "diff"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10
            )
            return res_unstaged.stdout
        except Exception as e:
            return f"Error fetching git diff: {str(e)}"

    @staticmethod
    def get_file_diff(file_path: str, repo_path: str = ".") -> str:
        """Returns git diff for a specific file path."""
        try:
            res = subprocess.run(
                ["git", "diff", "HEAD", "--", file_path],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10
            )
            return res.stdout if res.returncode == 0 else ""
        except Exception:
            return ""

    @staticmethod
    def list_file_tree(base_dir: str = "output") -> List[Dict[str, Any]]:
        """Returns a nested directory tree structure for the target output folder excluding ignored folders."""
        if not os.path.exists(base_dir):
            base_dir = "output" if os.path.exists("output") else "."

        ignore_dirs = {".git", "__pycache__", "node_modules", ".venv", ".next", "dist", "build"}

        def build_node(dir_path: str) -> List[Dict[str, Any]]:
            items = []
            try:
                entries = sorted(os.listdir(dir_path))
            except Exception:
                return items

            dirs = []
            files = []
            for entry in entries:
                if entry in ignore_dirs:
                    continue
                full_p = os.path.join(dir_path, entry)
                rel_p = os.path.relpath(full_p, ".").replace("\\", "/")
                
                if os.path.isdir(full_p):
                    children = build_node(full_p)
                    dirs.append({
                        "name": entry,
                        "path": rel_p,
                        "type": "directory",
                        "children": children
                    })
                elif os.path.isfile(full_p):
                    ext = os.path.splitext(entry)[1].lstrip('.').lower()
                    lang_map = {
                        "ts": "typescript", "tsx": "typescript",
                        "js": "javascript", "jsx": "javascript",
                        "py": "python", "json": "json",
                        "css": "css", "md": "markdown",
                        "sql": "sql", "yml": "yaml", "yaml": "yaml", "html": "html"
                    }
                    try:
                        stat = os.stat(full_p)
                        size = stat.st_size
                    except Exception:
                        size = 0

                    files.append({
                        "name": entry,
                        "path": rel_p,
                        "type": "file",
                        "language": lang_map.get(ext, "text"),
                        "size": size
                    })
            return dirs + files

        return build_node(base_dir)
