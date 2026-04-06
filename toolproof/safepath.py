"""Safe path handling — prevents path traversal, symlink escapes, and arbitrary writes.

Used by CLI and claude_reader to validate all user-controlled paths.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def validate_output_path(path: str | Path, allowed_dirs: list[Path] | None = None) -> Path:
    """Validate an output path is safe to write to.

    Rejects:
    - Symlinks (at any component)
    - Paths outside allowed directories
    - Paths to system directories
    """
    p = Path(path).resolve()

    # Reject if any component is a symlink
    check = Path(p.anchor)
    for part in p.parts[1:]:
        check = check / part
        if check.is_symlink():
            raise ValueError(f"Symlink detected in path: {check}")

    # Reject system directories
    system_dirs = ["/etc", "/usr", "/bin", "/sbin", "/boot", "/sys", "/proc", "/var/run"]
    for sd in system_dirs:
        if str(p).startswith(sd):
            raise ValueError(f"Cannot write to system directory: {sd}")

    # If allowed_dirs specified, check containment
    if allowed_dirs:
        resolved_allowed = [d.resolve() for d in allowed_dirs]
        if not any(str(p).startswith(str(d)) for d in resolved_allowed):
            raise ValueError(
                f"Path {p} is not within allowed directories: "
                f"{[str(d) for d in resolved_allowed]}"
            )

    return p


def validate_store_path(path: str | Path) -> Path:
    """Validate a receipt store path.

    Store paths must be within the user's home directory.
    """
    p = Path(path).resolve()
    home = Path.home().resolve()

    if not str(p).startswith(str(home)):
        raise ValueError(f"Store path must be within home directory: {p}")

    # Reject symlinks
    if p.exists() and p.is_symlink():
        raise ValueError(f"Store path is a symlink: {p}")

    return p


def validate_import_path(path: Path, base_dir: Path) -> Path:
    """Validate a file found by import is actually within the expected directory.

    Resolves symlinks and checks containment.
    """
    resolved = path.resolve()
    base_resolved = base_dir.resolve()

    if not str(resolved).startswith(str(base_resolved)):
        raise ValueError(
            f"File {path} resolves to {resolved} which is outside {base_resolved}"
        )

    return resolved
