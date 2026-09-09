"""Make bundled Qt and scientific-package DLLs discoverable on Windows."""

from __future__ import annotations

import os
import sys
from pathlib import Path


if sys.platform == "win32" and getattr(sys, "frozen", False):
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    dll_dirs = [
        bundle_root,
        bundle_root / "PySide6",
        bundle_root / "shiboken6",
        bundle_root / "numpy.libs",
        bundle_root / "pandas.libs",
    ]
    existing = [path for path in dll_dirs if path.is_dir()]
    for path in existing:
        try:
            os.add_dll_directory(os.fspath(path))
        except OSError:
            pass
    os.environ["PATH"] = os.pathsep.join(
        [os.fspath(path) for path in existing] + [os.environ.get("PATH", "")]
    )
