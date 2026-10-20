"""Open a Studio boot disk in MartyPC using an isolated writable runtime copy."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import marty_link


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disk', type=Path)
    parser.add_argument('--rgb', action='store_true', help='Start with RGB display instead of composite.')
    parser.add_argument('--runtime-root', type=Path, help='Store launch copies and logs in this directory.')
    args = parser.parse_args()
    try:
        link = marty_link.resolve_link()
        if link is None:
            raise ValueError('MartyPC was not found. Use Studio > Export > Link to MartyPC first.')
        process, log = marty_link.launch(link, args.disk, not args.rgb, run_root=args.runtime_root)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f'MartyPC could not start: {exc}\n')
    print(f'MartyPC launched (PID {process.pid}).\nDisk: {args.disk.resolve()}\nLog: {log}', flush=True)


if __name__ == '__main__':
    main()
