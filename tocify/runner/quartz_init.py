"""Initialize Quartz scaffold into a target directory with safe merge semantics."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_QUARTZ_REPO = "https://github.com/jackyzha0/quartz.git"
DEFAULT_QUARTZ_REF = "v4"

QUARTZ_SCAFFOLD_PATHS: tuple[str, ...] = (
    "quartz",
    "content",
    ".node-version",
    ".npmrc",
    ".prettierignore",
    ".prettierrc",
    "globals.d.ts",
    "index.d.ts",
    "package.json",
    "package-lock.json",
    "quartz.config.ts",
    "quartz.layout.ts",
    "tsconfig.json",
)

LOCAL_EXCLUDE_MARKER_START = "# >>> tocify quartz init >>>"
LOCAL_EXCLUDE_MARKER_END = "# <<< tocify quartz init <<<"
LOCAL_EXCLUDE_PATTERNS: tuple[str, ...] = (
    "/quartz/",
    "/content/",
    "/.quartz-cache/",
    "/public/",
    "/node_modules/",
    "/.node-version",
    "/.npmrc",
    "/.prettierignore",
    "/.prettierrc",
    "/globals.d.ts",
    "/index.d.ts",
    "/package.json",
    "/package-lock.json",
    "/quartz.config.ts",
    "/quartz.layout.ts",
    "/tsconfig.json",
)


@dataclass
class QuartzInitResult:
    target: Path
    source: Path
    created: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    overwritten: list[Path] = field(default_factory=list)
    missing_source_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    local_exclude_path: Path | None = None
    local_exclude_updated: bool = False
    local_exclude_would_update: bool = False


def _clone_quartz_source(repo_url: str, quartz_ref: str, destination: Path) -> Path:
    cmd = [
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        quartz_ref,
        repo_url,
        str(destination),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "unknown git clone error"
        raise RuntimeError(f"Unable to clone Quartz ({repo_url}@{quartz_ref}): {stderr}")
    return destination


def _gather_scaffold_files(source_root: Path) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    missing: list[str] = []

    for rel_path in QUARTZ_SCAFFOLD_PATHS:
        source_path = source_root / rel_path
        if not source_path.exists():
            missing.append(rel_path)
            continue
        if source_path.is_file():
            files.append(Path(rel_path))
            continue
        if source_path.is_dir():
            for candidate in sorted(source_path.rglob("*")):
                if candidate.is_file():
                    files.append(candidate.relative_to(source_root))
            continue
        missing.append(rel_path)

    files.sort(key=lambda p: p.as_posix())
    return files, missing


def _copy_file(
    source_file: Path,
    dest_file: Path,
    *,
    overwrite: bool,
    dry_run: bool,
    result: QuartzInitResult,
) -> None:
    if dest_file.exists():
        if not overwrite:
            result.skipped.append(dest_file)
            return
        if dest_file.is_dir():
            result.skipped.append(dest_file)
            result.warnings.append(
                f"Skip overwrite for directory path that collides with file: {dest_file}"
            )
            return
        if dry_run:
            result.overwritten.append(dest_file)
            return
        shutil.copy2(source_file, dest_file)
        result.overwritten.append(dest_file)
        return

    if dry_run:
        result.created.append(dest_file)
        return

    dest_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, dest_file)
    result.created.append(dest_file)


def _resolve_git_dir(target: Path) -> Path:
    git_path = target / ".git"
    if git_path.is_dir():
        return git_path

    if git_path.is_file():
        line = git_path.read_text(encoding="utf-8").strip()
        prefix = "gitdir:"
        if line.lower().startswith(prefix):
            relative_git_dir = line[len(prefix) :].strip()
            resolved = (target / relative_git_dir).resolve()
            if resolved.exists():
                return resolved

    raise RuntimeError(
        f"No .git directory found under {target}; cannot write local ignore rules."
    )


def _managed_exclude_block() -> str:
    lines = [LOCAL_EXCLUDE_MARKER_START, *LOCAL_EXCLUDE_PATTERNS, LOCAL_EXCLUDE_MARKER_END]
    return "\n".join(lines)


def append_local_excludes(target: Path, *, dry_run: bool = False) -> tuple[Path, bool, bool]:
    git_dir = _resolve_git_dir(target)
    exclude_path = git_dir / "info" / "exclude"
    block = _managed_exclude_block()

    existing = ""
    if exclude_path.exists():
        existing = exclude_path.read_text(encoding="utf-8")

    if LOCAL_EXCLUDE_MARKER_START in existing and LOCAL_EXCLUDE_MARKER_END in existing:
        return exclude_path, False, False

    if dry_run:
        return exclude_path, False, True

    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    separator = ""
    if existing:
        separator = "\n" if existing.endswith("\n") else "\n\n"
    updated = f"{existing}{separator}{block}\n"
    exclude_path.write_text(updated, encoding="utf-8")
    return exclude_path, True, False


def _init_quartz_from_source(
    *,
    source_root: Path,
    target: Path,
    overwrite: bool,
    dry_run: bool,
    write_local_exclude: bool,
) -> QuartzInitResult:
    result = QuartzInitResult(target=target, source=source_root)

    files_to_copy, missing_paths = _gather_scaffold_files(source_root)
    result.missing_source_paths.extend(missing_paths)

    for rel_path in files_to_copy:
        source_file = source_root / rel_path
        dest_file = target / rel_path
        _copy_file(source_file, dest_file, overwrite=overwrite, dry_run=dry_run, result=result)

    if write_local_exclude:
        try:
            exclude_path, updated, would_update = append_local_excludes(target, dry_run=dry_run)
            result.local_exclude_path = exclude_path
            result.local_exclude_updated = updated
            result.local_exclude_would_update = would_update
        except RuntimeError as exc:
            result.warnings.append(str(exc))

    return result


def init_quartz(
    *,
    target: Path,
    repo_url: str = DEFAULT_QUARTZ_REPO,
    quartz_ref: str = DEFAULT_QUARTZ_REF,
    overwrite: bool = False,
    dry_run: bool = False,
    write_local_exclude: bool = True,
    source_dir: Path | None = None,
) -> QuartzInitResult:
    """Initialize Quartz scaffold into target directory.

    Existing files are skipped by default unless overwrite=True.
    """
    target = target.expanduser().resolve()
    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)

    if source_dir is not None:
        source = source_dir.expanduser().resolve()
        if not source.exists() or not source.is_dir():
            raise RuntimeError(f"Source directory does not exist: {source}")
        return _init_quartz_from_source(
            source_root=source,
            target=target,
            overwrite=overwrite,
            dry_run=dry_run,
            write_local_exclude=write_local_exclude,
        )

    with tempfile.TemporaryDirectory(prefix="tocify-quartz-init-") as tmp_dir:
        source = _clone_quartz_source(repo_url, quartz_ref, Path(tmp_dir) / "quartz")
        return _init_quartz_from_source(
            source_root=source,
            target=target,
            overwrite=overwrite,
            dry_run=dry_run,
            write_local_exclude=write_local_exclude,
        )

