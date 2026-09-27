"""Summarize unmodified Marty core instruction-boundary and framebuffer captures."""
from pathlib import Path
import argparse, collections, csv, hashlib, json

def summarize(base: Path, phase: int):
    options_path = base / f"phase{phase}-cpu-options.json"
    if not options_path.is_file():
        raise ValueError(f"{options_path}: CPU timing options were not recorded; rerun with the corrected harness before claiming validation")
    cpu_options = json.loads(options_path.read_text(encoding="utf-8"))
    if cpu_options.get("enable_wait_states") is not True or cpu_options.get("dram_refresh_schedule_enabled_at_first_out") is not True:
        raise ValueError(f"{options_path}: active CPU waits and DRAM refresh are required")
    if (cpu_options.get("pit1_reload_at_first_out") != 19
            or cpu_options.get("pit1_counting_at_first_out") is not True
            or cpu_options.get("pit1_retrigger_at_first_out") is not True
            or cpu_options.get("pit1_mode_at_first_out") != "RateGenerator"):
        raise ValueError(f"{options_path}: PIT1 must be counting in mode 2 with reload 19")
    path = base / f"phase{phase}.csv"
    rows = list(csv.DictReader(path.open()))
    streams = collections.defaultdict(list)
    for row in rows:
        if row["port"] == "03D9" and row["value"] in ("0C", "00", "3C", "30"):
            streams[(row["cs"], row["ip"], row["value"])].append(row)
    result = {"phase": phase, "cpu_options_at_first_out": cpu_options, "streams": []}
    for (cs, ip, value), stream in streams.items():
        if len(stream) < 4:
            continue
        steady = stream
        positions = collections.Counter((int(r["beam_x_after"]), int(r["beam_y_after"])) for r in steady)
        cycles = [int(r["cpu_cycle"]) for r in steady]
        result["streams"].append({"cs": cs, "ip": ip, "value": value, "observations": len(stream), "discarded_initial": 0, "first_observation": stream[0], "instruction_end_beam_positions": [[*xy,n] for xy,n in sorted(positions.items())], "cpu_cycle_periods": sorted(collections.Counter(b-a for a,b in zip(cycles,cycles[1:])).items())})
    frames = list(csv.DictReader((base / f"phase{phase}-frames.csv").open()))
    steadyframes = frames
    result["frame_count"] = len(frames)
    result["first_completed_marked_frame"] = frames[0] if frames else None
    result["cropped_visible_frame_hashes"] = dict(collections.Counter(f.get("cropped_fnv64", "unavailable") for f in frames))
    result["steady_frame_hashes"] = dict(collections.Counter(f["fnv64"] for f in steadyframes))
    result["steady_red_bounding_boxes"] = dict(collections.Counter(",".join(f[key] for key in ("red_x_min","red_y_min","red_x_max","red_y_max","red_pixels")) for f in steadyframes))
    data = (base / f"phase{phase}-frame.bin").read_bytes()
    result["last_frame_sha256"] = hashlib.sha256(data).hexdigest()
    try:
        from PIL import Image
        # CGA's raw direct-render buffer stores one RGBI index per master-clock dot.
        colors = [(0,0,0),(0,0,170),(0,170,0),(0,170,170),(170,0,0),(170,0,170),(170,85,0),(170,170,170),(85,85,85),(85,85,255),(85,255,85),(85,255,255),(255,85,85),(255,85,255),(255,255,85),(255,255,255)]
        width=912
        im=Image.new("RGB",(width,len(data)//width))
        im.putdata([colors[b&15] for b in data])
        im.save(base / f"phase{phase}-frame.png")
    except ImportError:
        pass
    return result

if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory",type=Path,default=Path(__file__).resolve().parents[1]/"external/research/startlock-validation/waitstates-on")
    p.add_argument("--phases",type=int,nargs="+",default=[0,1,2,3])
    a=p.parse_args()
    result={"scope":"Emulated IBM 5160 + CGA + GLaBIOS 0.2.6, unmodified MartyPC core. Beam positions sampled after OUT instruction execution; these are not the exact register-latch instant or physical hardware measurements.","phases":[summarize(a.directory,ph) for ph in a.phases]}
    (a.directory/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))



