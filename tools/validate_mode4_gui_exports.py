"""Check saved GUI exports against NASM and the wait-state-enabled core."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.validate_mode4_release import inspect_run
import cga_mode4_lock as lock


def main():
    work = ROOT / "external/research/mode4-gui"
    exe = ROOT / "external/research/imagelock-validation/target/release/validate_imagelock.exe"
    nasm = Path.home() / "AppData/Local/bin/NASM/nasm.exe"
    cases = json.loads((work / "gui-results.json").read_text())

    def run(item):
        name = item["case"]
        program = work / f"{name}.com"
        rebuilt = work / f"{name}-rebuilt.com"
        subprocess.run([str(nasm), "-f", "bin", str(work / f"{name}.asm"), "-o", str(rebuilt)], check=True)
        assert rebuilt.read_bytes() == program.read_bytes()
        phase = int(name[3:]) % 4
        folder = work / name
        folder.mkdir(exist_ok=True)
        expected = work / f"{name}.bin"
        ip = lock.descriptor(program.read_bytes())["first_out_ip"]
        result = subprocess.run([str(exe), str(ROOT), str(program), str(phase), "16000000",
                                 str(folder), f"{ip:X}", str(expected)], capture_output=True, text=True, timeout=600)
        (folder / "run.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stderr
        record = {**item, **inspect_run(folder, phase, program, expected, 1), "asm_roundtrip": True}
        print(f"PASS {name}: {record['visible_frames']} exact frames; ASM byte-exact", flush=True)
        return record

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(run, cases))
    (work / "validation.json").write_text(json.dumps({"status": "passed", "cases": records,
        "visible_frames": sum(r["visible_frames"] for r in records)}, indent=2) + "\n")


if __name__ == "__main__":
    main()
