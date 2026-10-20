"""Run a preserved Python source from Old Storage using the repository paths.

Examples (from the repository root):
    .venv\\Scripts\\python.exe tools\\run_archived.py --list
    .venv\\Scripts\\python.exe tools\\run_archived.py generate_cgalk11_dense_test.py --help
    .venv\\Scripts\\python.exe tools\\run_archived.py cga_v166.py

Generators retain their original behavior, including writing outputs to files/.
Historical sources remain unchanged in the archive.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import runpy
import sys
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "Old Storage" / "legacy-root"
LEGACY_APPLICATIONS = {"cga_v165.py", "cga_v166.py"}


def archived_scripts() -> list[str]:
    """List only Python files directly inside the historical source archive."""
    archive = ARCHIVE.resolve()
    return sorted(
        path.name
        for path in ARCHIVE.glob("*.py")
        if path.is_file() and path.resolve().parent == archive
    )


def load_legacy_application(path: Path) -> ModuleType:
    """Load an old application without opening its GUI.

    Historical v166 finds the DOS boot template beside its original root-level
    source location. Restore that resource anchor after loading the preserved
    code; the imported functions use this module's globals when called later.
    """
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load archived application: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    module.__file__ = str(ROOT / path.name)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run an unchanged archived Python source with repository paths.",
        epilog=(
            "Use --list to see available filenames. Arguments after the filename "
            "are passed to that script. Generators may write to files/."
        ),
    )
    parser.add_argument("--list", action="store_true", help="list archived Python sources")
    parser.add_argument("script", nargs="?", help="archived .py filename (no directory)")
    parser.add_argument("script_args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.list:
        if args.script is not None:
            parser.error("--list cannot be combined with a script")
        print("\n".join(archived_scripts()) or "No archived Python sources found.")
        return 0
    if args.script is None:
        parser.print_help()
        return 0
    if (
        "/" in args.script
        or "\\" in args.script
        or Path(args.script).name != args.script
        or args.script not in archived_scripts()
    ):
        parser.error("script must be an archived .py filename; use --list to see choices")

    source = ARCHIVE / args.script
    os.chdir(ROOT)
    sys.path[:0] = [str(ROOT), str(ARCHIVE)]
    sys.argv = [str(source), *args.script_args]
    if source.name in LEGACY_APPLICATIONS:
        load_legacy_application(source).main()
    else:
        runpy.run_path(str(source), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
