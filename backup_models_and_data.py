#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backup .gitignore files PLUS all model/data folders, keeping project paths.

Runs on Windows CMD using Python 3.10+. Uses only the Python standard library
and git; no upload is performed. No Python env or node_modules copied.
Secrets (.env and common credential files) excluded by default.
"""

import argparse
from datetime import datetime
import fnmatch
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from zipfile import ZIP_STORED, ZipFile

EXCLUDED_NAMES = {"venv", ".venv", "node_modules", ".git"}
RESOURCE_NAMES = {
    "data", "dataset", "datasets", "models", "model", "checkpoints",
    "checkpoint", "weights", "hf-cache",
}
MODEL_EXTENSIONS = {
    ".pt", ".pth", ".ckpt", ".safetensors", ".onnx", ".gguf",
    ".ggml", ".joblib", ".pkl", ".h5", ".keras", ".tflite",
}
SENSITIVE_NAMES = {".env", "credentials.json", "secrets.json", "service-account.json"}
SENSITIVE_EXTENSIONS = {".pem", ".key", ".p12", ".pfx"}


def is_excluded_component(part: str) -> bool:
    lower = part.casefold()
    return lower in EXCLUDED_NAMES or lower.startswith(".venv-")


def has_excluded_directory(rel: Path) -> bool:
    return any(is_excluded_component(p) for p in rel.parts[:-1])


def is_sensitive(rel: Path) -> bool:
    name = rel.name.casefold()
    return (name in SENSITIVE_NAMES or name.startswith(".env.")
            or Path(name).suffix in SENSITIVE_EXTENSIONS
            or fnmatch.fnmatch(name, "*secret*key*"))


def is_valid_file(root: Path, rel: Path, include_secrets: bool) -> bool:
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        return False
    if has_excluded_directory(rel):
        return False
    if not include_secrets and is_sensitive(rel):
        return False
    file = root / rel
    if not file.is_file() or file.is_symlink():
        return False
    try:
        return file.resolve().is_relative_to(root)
    except (OSError, RuntimeError):
        return False


def git_ignored_files(root: Path) -> set[Path]:
    """Match root and nested .gitignore; only ignored, non-tracked files."""
    exclusions = []
    for name in ("venv", ".venv", ".venv-*", "node_modules", ".git"):
        exclusions += [f":(exclude){name}/**", f":(exclude)**/{name}/**"]
    cmd = ["git", "ls-files", "--others", "--ignored", "-z",
           "--exclude-per-directory=.gitignore", "--", ".", *exclusions]
    res = subprocess.run(cmd, cwd=root, capture_output=True, check=False)
    if res.returncode:
        raise RuntimeError(res.stderr.decode("utf-8", errors="replace").strip())
    found = set()
    for raw in res.stdout.split(b"\x00"):
        if raw:
            p = PurePosixPath(os.fsdecode(raw))
            found.add(Path(*p.parts))
    return found


def resource_files(root: Path) -> set[Path]:
    """Always capture resource folders even if files are tracked/not ignored."""
    found = set()
    for folder, dirs, filenames in os.walk(root, followlinks=False):
        base = Path(folder)
        relative_base = base.relative_to(root)
        dirs[:] = [d for d in dirs if not is_excluded_component(d)
                   and not (base / d).is_symlink()]
        in_resource = any(part.casefold() in RESOURCE_NAMES
                          for part in relative_base.parts)
        for name in filenames:
            f = base / name
            if f.is_symlink():
                continue
            rel = f.relative_to(root)
            if in_resource or f.suffix.casefold() in MODEL_EXTENSIONS:
                found.add(rel)
    return found


def readable_size(size: int) -> str:
    n = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def main() -> int:
    parser = argparse.ArgumentParser(description="Sao luu ignored files + models/data cho PulmoGraph AI")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent,
                        help="Thu muc goc project; mac dinh thu muc chua script")
    parser.add_argument("--output", type=Path, help="Duong dan ZIP/thu muc dau ra, phai ngoai project")
    parser.add_argument("--folder", action="store_true", help="Tao thu muc thay vi ZIP")
    parser.add_argument("--dry-run", action="store_true", help="Thong ke, khong sao chep")
    parser.add_argument("--list", action="store_true", help="In tat ca duong dan duoc chon")
    parser.add_argument("--include-secrets", action="store_true",
                        help="BAO MAT: gom ca .env, private keys (khong khuyen nghi chia se)")
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print("[ERROR] Khong tim thay thu muc du an", file=sys.stderr)
        return 2
    # The project itself must be a Git repo for the ignored-file half.
    res = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root,
                         capture_output=True, text=True, check=False)
    if res.returncode or Path(res.stdout.strip()).resolve() != root:
        print("[ERROR] Chay o thu muc goc repository (git init neu chua co).", file=sys.stderr)
        return 2

    suffix = "" if args.folder else ".zip"
    default_name = f"{root.name}_models_data_{datetime.now():%Y%m%d_%H%M%S}{suffix}"
    output = (args.output or root.parent / default_name).resolve()
    if output == root or output.is_relative_to(root):
        print("[ERROR] Dat output NGOAI thu muc du an de tranh sao chep lap.", file=sys.stderr)
        return 2
    if not args.folder and output.suffix.casefold() != ".zip":
        print("[ERROR] Output phai la file .zip (hoac them --folder).", file=sys.stderr)
        return 2
    if output.exists():
        print(f"[ERROR] Output da ton tai: {output}", file=sys.stderr)
        return 2

    try:
        ignored = git_ignored_files(root)
        resource = resource_files(root)
        selected = sorted((rel for rel in ignored | resource
                           if is_valid_file(root, rel, args.include_secrets)),
                          key=lambda x: x.as_posix().casefold())
        total = sum((root / rel).stat().st_size for rel in selected)
    except (OSError, RuntimeError) as exc:
        print(f"[ERROR] Khong the quet du an: {exc}", file=sys.stderr)
        return 2

    print(f"Project       : {root}")
    print(f"Backup        : {output}")
    print(f"Gitignored    : {len(ignored)} duong dan")
    print(f"Resource files: {len(resource)} file models/data")
    print(f"Files selected: {len(selected)}")
    print(f"Total         : {readable_size(total)}")
    print("Excluded dirs : venv/ .venv/ .venv-*/ node_modules/ .git/")
    if not args.include_secrets:
        print("Secrets       : KHONG sao luu .env, private keys, credentials")
    else:
        print("[WARNING] Backup co the chua mat khau/token! Khong chia se ZIP cong khai.")
    shown = selected if args.list else selected[:20]
    for rel in shown:
        print("  " + rel.as_posix())
    if not args.list and len(selected) > len(shown):
        print(f"  ... va {len(selected) - len(shown)} tep nua")
    if args.dry_run or not selected:
        print("[DRY RUN] Khong tao ban sao." if args.dry_run else "Khong co du lieu.")
        return 0

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        needed = total + max(32 * 1024**2, total // 100)
        available = shutil.disk_usage(output.parent).free
        if available < needed:
            print(f"[ERROR] Khong du cho trong: {readable_size(available)} < {readable_size(needed)}", file=sys.stderr)
            return 3
        if args.folder:
            output.mkdir(parents=True, exist_ok=False)
            for i, rel in enumerate(selected, 1):
                dest = output / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / rel, dest)
                if i % 100 == 0 or i == len(selected):
                    print(f"Copied {i}/{len(selected)}")
        else:
            tmp = output.with_name(output.name + ".partial")
            if tmp.exists():
                print(f"[ERROR] File tam da ton tai: {tmp}", file=sys.stderr)
                return 2
            try:
                with ZipFile(tmp, "w", compression=ZIP_STORED, allowZip64=True) as zf:
                    for i, rel in enumerate(selected, 1):
                        zf.write(root / rel, arcname=rel.as_posix())
                        if i % 100 == 0 or i == len(selected):
                            print(f"Packed {i}/{len(selected)}")
                tmp.replace(output)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise
    except (OSError, RuntimeError) as exc:
        print(f"[ERROR] Sao luu that bai: {exc}", file=sys.stderr)
        return 4

    print("\n[OK] Hoan tat: " + str(output))
    print("Giai nen NOI DUNG ZIP vao thu muc goc da clone tu GitHub (giu duong dan).")
    print("Luu y: Data y khoa can duoc phep sao luu va chia se, du cho repository o che do Private.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
