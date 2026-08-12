from __future__ import annotations

from pathlib import Path
import os


def search_generator(roots: list[str], terms: list[str], project_root: Path) -> dict:
    matches = []
    extensions = {".py", ".sql", ".yaml", ".yml", ".json", ".md", ".txt"}
    for configured in roots:
        root = (project_root / configured).resolve()
        if not root.exists(): continue
        for directory, names, files in os.walk(root, onerror=lambda _: None):
            names[:] = [name for name in names if name not in {".git", ".pytest_cache", "node_modules", "output", "reports"}]
            for filename in files:
                path = Path(directory) / filename
                if path.suffix.lower() not in extensions: continue
                try: text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError: continue
                found = [term for term in terms if term.lower() in text.lower()]
                if found: matches.append({"file": str(path), "matched_terms": found})
    return {"status": "FOUND" if matches else "GENERATOR_LOGIC_NOT_AVAILABLE", "matches": matches,
            "finding": "No generator relationship may be inferred when source is unavailable." if not matches else "Manual review required; source files are never modified."}
