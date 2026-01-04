import argparse
import os
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any


def run(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return res.stdout
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        if stderr:
            print(stderr)
        raise


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_state(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): (v if isinstance(v, dict) else {}) for k, v in data.items()}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp_path, path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Update local server_mirror/ by downloading a filtered subset of files from the VM. "
            "Skips bulky data directories (market_logs, vm_logs, venv, caches)."
        )
    )
    parser.add_argument("--host", default="34.56.193.18")
    parser.add_argument("--user", default="jetpackjules")
    parser.add_argument(
        "--key",
        default=str(Path(__file__).resolve().parent / "keys" / "gcp_key"),
        help="Path to SSH private key",
    )
    parser.add_argument(
        "--remote-root",
        default="/home/jetpackjules",
        help="Remote root to mirror",
    )
    parser.add_argument(
        "--local-dir",
        default=str(Path(__file__).resolve().parent / "server_mirror"),
        help="Local destination directory",
    )
    parser.add_argument(
        "--include-logs",
        action="store_true",
        help="Also mirror *.log files (can be large).",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete local mirrored files that are no longer present on the server (within the filtered set only).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be copied/deleted without doing it.",
    )

    args = parser.parse_args()

    key_path = str(Path(args.key).expanduser().resolve())
    local_dir = Path(args.local_dir).expanduser().resolve()
    ensure_dir(local_dir)

    state_path = local_dir / ".mirror_state.json"
    state = load_state(state_path)

    ssh_base = [
        "ssh",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-i",
        key_path,
        f"{args.user}@{args.host}",
    ]

    # Build remote find command.
    include_parts = [
        "-name '*.py'",
        "-o -name '*.json'",
        "-o -name '*.html'",
        "-o -name '*.sh'",
        "-o -name 'trading_enabled.txt'",
        "-o -name 'trades.csv'",
    ]
    if args.include_logs:
        include_parts.append("-o -name '*.log'")

    # NOTE: find requires escaped parentheses when invoked via a shell.
    include_expr = "\\( " + " ".join(include_parts) + " \\)"

    # Excludes: bulky or non-source dirs.
    excludes = [
        "-not -path './market_logs/*'",
        "-not -path './snapshots/*'",
        "-not -path './vm_logs/*'",
        "-not -path './venv/*'",
        "-not -path './kalshi_venv/*'",
        "-not -path './__pycache__/*'",
        "-not -path './.cache/*'",
        "-not -path './.config/*'",
        "-not -path './.local/*'",
    ]

    # Limit depth to keep it quick, but include a couple nested folders (e.g., live_trading_system/).
    remote_find = (
        f"cd {shlex.quote(args.remote_root)} && "
        f"find . -maxdepth 4 -type f {include_expr} "
        + " ".join(excludes)
        + " -printf '%P\t%T@\t%s\\n'"
    )

    stdout = run(ssh_base + [remote_find])

    # Parse: rel_path<TAB>mtime_epoch_float<TAB>size_bytes
    remote_meta: dict[str, dict[str, Any]] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        rel, mtime_s, size_s = parts
        rel = rel.strip().lstrip("/")
        try:
            mtime = int(float(mtime_s))
            size = int(size_s)
        except ValueError:
            continue
        if not rel:
            continue
        remote_meta[rel] = {"remote_mtime": mtime, "remote_size": size}

    rel_paths = sorted(remote_meta.keys())

    # Copy each file.
    scp_base = [
        "scp",
        "-o",
        "StrictHostKeyChecking=no",
        "-i",
        key_path,
    ]

    copied = 0
    skipped = 0
    for rel in rel_paths:
        remote_path = f"{args.user}@{args.host}:{args.remote_root}/{rel}"
        local_path = local_dir / rel
        ensure_dir(local_path.parent)

        remote_mtime = int(remote_meta[rel]["remote_mtime"])
        remote_size = int(remote_meta[rel]["remote_size"])

        prev = state.get(rel, {})
        prev_mtime = prev.get("remote_mtime")
        prev_size = prev.get("remote_size")

        should_copy = True
        if local_path.exists() and isinstance(prev_mtime, int) and isinstance(prev_size, int):
            if prev_mtime == remote_mtime and prev_size == remote_size:
                should_copy = False
        elif local_path.exists():
            # If we don't have state yet but the file exists locally, skip downloading
            # when sizes match. This avoids re-downloading an existing mirror on first run.
            try:
                if local_path.stat().st_size == remote_size:
                    should_copy = False
            except OSError:
                pass

        if args.dry_run:
            action = "COPY" if should_copy else "SKIP"
            print(f"{action} {remote_path} -> {local_path}")
            if should_copy:
                copied += 1
            else:
                skipped += 1
            continue

        if not should_copy:
            skipped += 1
            state[rel] = {"remote_mtime": remote_mtime, "remote_size": remote_size}
            continue

        try:
            subprocess.run(scp_base + [remote_path, str(local_path)], check=True)
            copied += 1
            state[rel] = {"remote_mtime": remote_mtime, "remote_size": remote_size}
        except subprocess.CalledProcessError as e:
            print(f"WARN: failed to copy {rel}: {e}")

    deleted = 0
    if args.prune:
        allowed_suffixes = {".py", ".json", ".html", ".sh", ".csv"}
        if args.include_logs:
            allowed_suffixes.add(".log")

        remote_set = set(rel_paths)
        for path in local_dir.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(local_dir)).replace("\\", "/")

            if rel in {"market_logs", "snapshots", "vm_logs"} or rel.startswith("market_logs/") or rel.startswith("vm_logs/"):
                continue

            # Only prune files in the filtered set types.
            if path.name in {"trading_enabled.txt", "trades.csv"}:
                pass
            elif path.suffix.lower() not in allowed_suffixes:
                continue

            if rel not in remote_set:
                if args.dry_run:
                    print(f"DELETE {path}")
                else:
                    try:
                        path.unlink()
                        deleted += 1
                        state.pop(rel, None)
                    except OSError as e:
                        print(f"WARN: failed to delete {path}: {e}")

    if not args.dry_run:
        save_state(state_path, state)

    print(f"Done. Copied {copied} files into {local_dir}. Skipped {skipped} unchanged files.")
    if args.prune:
        print(f"Pruned {deleted} local files.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
