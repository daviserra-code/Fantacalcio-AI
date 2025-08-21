# export_changes.py
# Create a compact JSON payload of changed files in your repo.
# Works with or without git; can split output to multiple JSON parts if large.

import os, sys, json, base64, hashlib, argparse, subprocess, shlex, datetime
from pathlib import Path

DEFAULT_INCLUDE_EXT = {
    ".py",".html",".htm",".js",".ts",".css",".json",".yml",".yaml",
    ".jinja",".jinja2",".env",".ini",".cfg",".toml",".md"
}
DEFAULT_EXCLUDE_DIRS = {
    ".git","node_modules",".venv","venv","__pycache__",".mypy_cache",
    ".pytest_cache",".ipynb_checkpoints",".pythonlibs","chroma_db","cache","data/exports"
}
DEFAULT_EXCLUDE_GLOBS = {
    "*.png","*.jpg","*.jpeg","*.webp","*.gif","*.bmp","*.ico",
    "*.db","*.sqlite","*.sqlite3","*.parquet","*.feather",
    "*.jsonl","*.log","*.lock","*.zip","*.tar","*.gz"
}

def sha1_bytes(b: bytes) -> str:
    h = hashlib.sha1(); h.update(b); return h.hexdigest()

def is_text_bytes(b: bytes) -> bool:
    try:
        b.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False

def git_available() -> bool:
    try:
        subprocess.check_output(["git","rev-parse","--is-inside-work-tree"], stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def run(cmd: str) -> str:
    return subprocess.check_output(shlex.split(cmd), stderr=subprocess.DEVNULL).decode("utf-8", "ignore")

def list_changed_with_git(git_range: str|None) -> list[str]:
    if git_range:
        out = run(f"git diff --name-only {git_range}")
        files = [p.strip() for p in out.splitlines() if p.strip()]
        if files:
            return files
    out = run("git ls-files -m -o --exclude-standard")
    files = [p.strip() for p in out.splitlines() if p.strip()]
    return files

def looks_excluded(path: Path, exclude_dirs: set[str], exclude_globs: set[str]) -> bool:
    parts = set(p.lower() for p in path.parts)
    if any(d.lower() in parts for d in exclude_dirs):
        return True
    name = path.name.lower()
    for pat in exclude_globs:
        if Path(name).match(pat):
            return True
    return False

def fallback_scan(root: Path, since_ts: float | None, include_ext: set[str],
                  exclude_dirs: set[str], exclude_globs: set[str]) -> list[str]:
    picked: list[str] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if looks_excluded(p.relative_to(root), exclude_dirs, exclude_globs):
            continue
        if p.suffix.lower() not in include_ext:
            continue
        if since_ts is not None:
            try:
                if p.stat().st_mtime < since_ts:
                    continue
            except Exception:
                continue
        picked.append(str(p.relative_to(root)))
    return picked

def collect_files(root: Path, rel_paths: list[str], max_file_bytes: int) -> list[dict]:
    items = []
    for rel in rel_paths:
        abs_p = root / rel
        try:
            b = abs_p.read_bytes()
        except Exception:
            continue
        if len(b) > max_file_bytes:
            continue
        meta = {
            "path": rel.replace("\\","/"),
            "size": len(b),
            "sha1": sha1_bytes(b),
            "mtime": int(abs_p.stat().st_mtime),
        }
        if is_text_bytes(b):
            meta["is_binary"] = False
            meta["encoding"] = "utf-8"
            meta["content"] = b.decode("utf-8")
        else:
            meta["is_binary"] = True
            meta["encoding"] = "base64"
            meta["content_b64"] = base64.b64encode(b).decode("ascii")
        items.append(meta)
    return items

def write_payload(payload: dict, out_path: Path, max_bytes: int|None):
    js = json.dumps(payload, ensure_ascii=False, separators=(",",":"))
    if max_bytes and len(js.encode("utf-8")) > max_bytes:
        files = payload["files"]
        header = {k:v for k,v in payload.items() if k!="files"}
        parts = []
        chunk = []
        current = 0
        for f in files:
            test = json.dumps({"files":[f]}, ensure_ascii=False, separators=(",",":")).encode("utf-8")
            if current + len(test) > max_bytes and chunk:
                parts.append(chunk); chunk=[]; current=0
            chunk.append(f)
            current += len(test)
        if chunk:
            parts.append(chunk)
        written = []
        for i,chunk in enumerate(parts, start=1):
            part_payload = dict(header); part_payload["files"] = chunk
            part_name = out_path.with_name(out_path.stem + f".part{i}" + out_path.suffix)
            part_name.write_text(json.dumps(part_payload, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
            written.append(str(part_name))
        return written
    else:
        out_path.write_text(js, encoding="utf-8")
        return [str(out_path)]

def main():
    ap = argparse.ArgumentParser(description="Export changed app files to JSON.")
    ap.add_argument("--root", default=".", help="Project root")
    ap.add_argument("--git-range", default=None, help="Git diff range, e.g. origin/main...HEAD")
    ap.add_argument("--since", default=None, help="Only include files modified since ISO time (e.g. 2025-08-13T00:00:00)")
    ap.add_argument("--max-file-bytes", type=int, default=400_000, help="Skip any single file larger than this")
    ap.add_argument("--max-json-bytes", type=int, default=900_000, help="Split JSON into parts under this size (UTF-8 bytes)")
    ap.add_argument("--include-ext", default=",".join(sorted(DEFAULT_INCLUDE_EXT)))
    ap.add_argument("--exclude-dirs", default=",".join(sorted(DEFAULT_EXCLUDE_DIRS)))
    ap.add_argument("--exclude-globs", default=",".join(sorted(DEFAULT_EXCLUDE_GLOBS)))
    ap.add_argument("--out", default="app_changes.json", help="Output JSON (or prefix for parts)")
    ap.add_argument("--force-scan", action="store_true", help="Ignore git and scan the tree (respects --since if provided)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    include_ext = set(s.strip().lower() for s in args.include_ext.split(",") if s.strip())
    exclude_dirs = set(s.strip() for s in args.exclude_dirs.split(",") if s.strip())
    exclude_globs = set(s.strip() for s in args.exclude_globs.split(",") if s.strip())

    since_ts = None
    if args.since:
        try:
            dt = datetime.datetime.fromisoformat(args.since)
            since_ts = dt.timestamp()
        except Exception:
            print(f"Warning: could not parse --since '{args.since}', ignoring.", file=sys.stderr)

    if git_available() and not args.force_scan:
        rel_paths = list_changed_with_git(args.git_range)
    else:
        rel_paths = []

    if not rel_paths:
        rel_paths = fallback_scan(root, since_ts, include_ext, exclude_dirs, exclude_globs)

    rel_paths = sorted(set(rel_paths))
    files = collect_files(root, rel_paths, args.max_file_bytes)

    git_info = {}
    if git_available():
        try:
            git_info["head"] = run("git rev-parse HEAD").strip()
            git_info["branch"] = run("git rev-parse --abbrev-ref HEAD").strip()
            git_info["status"] = run("git status --porcelain")
        except Exception:
            pass

    payload = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "root": str(root),
        "git": git_info,
        "filters": {
            "git_range": args.git_range,
            "since": args.since,
            "include_ext": sorted(include_ext),
            "exclude_dirs": sorted(exclude_dirs),
            "exclude_globs": sorted(exclude_globs),
            "max_file_bytes": args.max_file_bytes
        },
        "summary": {
            "file_count": len(files),
            "total_bytes": sum(f["size"] for f in files)
        },
        "files": files
    }

    out_path = (Path.cwd() / args.out).resolve()
    written = write_payload(payload, out_path, args.max_json_bytes)
    kb = payload["summary"]["total_bytes"]/1024.0
    print(f"✓ Exported {len(files)} files ({kb:.1f} KB payload) ->")
    for p in written:
        print("   ", p)

if __name__ == "__main__":
    main()
