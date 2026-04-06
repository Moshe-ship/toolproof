"""Safe path handling — prevents path traversal, symlink escapes, and arbitrary writes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _is_parent(parent: Path, child: Path) -> bool:
    """Check if parent is an ancestor of child using pathlib (not string prefix).

    This is the correct way — Path.is_relative_to() handles edge cases
    that str.startswith() misses (e.g., /home_evil vs /home).
    """
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _reject_symlinks(path: Path) -> None:
    """Walk every existing component and reject symlinks."""
    check = Path(path.anchor)
    for part in path.parts[1:]:
        check = check / part
        if check.exists() and check.is_symlink():
            raise ValueError(f"Symlink detected in path: {check}")


def validate_output_path(path: str | Path) -> Path:
    """Validate an output path is safe to write to.

    Rules:
    - No symlinks at any path component
    - Not in system directories
    - Must be within user's home directory
    """
    p = Path(path).resolve()
    home = Path.home().resolve()

    # Must be within home directory
    if not _is_parent(home, p):
        raise ValueError(f"Output path must be within home directory: {p}")

    _reject_symlinks(p)

    # Reject system directories
    system_dirs = ["/etc", "/usr", "/bin", "/sbin", "/boot", "/sys", "/proc", "/var/run"]
    for sd in system_dirs:
        sd_path = Path(sd).resolve()
        if _is_parent(sd_path, p):
            raise ValueError(f"Cannot write to system directory: {sd}")

    return p


def validate_store_path(path: str | Path) -> Path:
    """Validate a receipt store path. Must be within home directory."""
    p = Path(path).resolve()
    home = Path.home().resolve()

    if not _is_parent(home, p):
        raise ValueError(f"Store path must be within home directory: {p}")

    if p.exists() and p.is_symlink():
        raise ValueError(f"Store path is a symlink: {p}")

    return p


def validate_import_path(path: Path, base_dir: Path) -> Path:
    """Validate an import file is actually within the expected directory.

    Resolves symlinks and checks containment using pathlib ancestry.
    """
    resolved = path.resolve()
    base_resolved = base_dir.resolve()

    if not _is_parent(base_resolved, resolved):
        raise ValueError(
            f"File {path} resolves to {resolved} which is outside {base_resolved}"
        )

    return resolved
