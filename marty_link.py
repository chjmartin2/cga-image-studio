"""Optional MartyPC 0.5 configuration/launch integration; no emulator bundled."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib


def settings_dir():
    return Path(os.environ.get('LOCALAPPDATA', Path.home()/'.local/share'))/'CGAImageStudio'


def validate_link(executable, config):
    exe, cfg = Path(executable).resolve(), Path(config).resolve()
    if not exe.is_file() or exe.suffix.lower() != '.exe':
        raise ValueError('Select an installed MartyPC executable (.exe).')
    if not cfg.is_file():
        raise ValueError('Select the working MartyPC main TOML configuration.')
    data = tomllib.loads(cfg.read_text(encoding='utf-8-sig'))
    if str(data.get('meta', {}).get('config_version')) != '0.5':
        raise ValueError('This integration supports MartyPC 0.5 configuration files.')
    emu = data.get('emulator', {})
    base = Path(emu.get('basedir', '.'))
    if not base.is_absolute():
        base = cfg.parent/base
    resources = emu.get('paths', [])
    for resource in ('machine', 'rom'):
        paths = [Path(p['path'].replace('$basedir$', base.as_posix()))
                 for p in resources if p.get('resource') == resource]
        paths = [p if p.is_absolute() else cfg.parent/p for p in paths]
        if not any(p.is_dir() and any(f.is_file() for f in p.rglob('*')) for p in paths):
            raise ValueError(f'MartyPC {resource} resources are missing. Select the configuration from a working installation with ROMs.')
    if not data.get('machine', {}).get('config_name'):
        raise ValueError('The configuration must select a working machine with a floppy drive.')
    if not emu.get('scaler_preset'):
        raise ValueError('No display presets found in the selected configuration.')
    return {'executable': str(exe), 'config': str(cfg)}


def save_link(link):
    folder = settings_dir()
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder/'marty-link.tmp'
    temporary.write_text(json.dumps(link, indent=2), encoding='utf-8')
    temporary.replace(folder/'marty-link.json')


def load_link():
    path = settings_dir()/'marty-link.json'
    if not path.exists():
        return None
    return validate_link(**json.loads(path.read_text(encoding='utf-8')))


def project_link(root=None):
    """Find this checkout's working source build, without changing preferences."""
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    executable = root/'external/martypc/target/release/martypc.exe'
    config = root/'external/martypc/install/martypc-cga.toml'
    if not executable.is_file() or not config.is_file():
        return None
    return validate_link(executable, config)


def resolve_link():
    """Use a linked installation, relocating this project's pre-migration link."""
    root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    path = settings_dir()/'marty-link.json'
    saved = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    suffixes = {'executable': 'external/martypc/target/release/martypc.exe',
                'config': 'external/martypc/install/martypc-cga.toml'}
    project_layout = isinstance(saved, dict) and all(
        str(saved.get(key, '')).replace('\\', '/').lower().endswith('/'+suffix)
        for key, suffix in suffixes.items())
    # An unrelated, explicitly linked installation is independent of the
    # health (or presence) of the optional build in this checkout.
    if saved is not None and not project_layout:
        return validate_link(**saved)
    local = project_link(root)
    # The master checkout may have moved while an older frozen copy still
    # exists. Do not run that archive merely because the old paths are valid.
    if local is not None:
        return local
    return validate_link(**saved) if saved is not None else None


def create_run_dir(parent=None):
    folder = Path(parent) if parent is not None else settings_dir()/'marty-runs'
    folder.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix='studio-', dir=folder))


def launch_config(text, disk, composite, floppy_type=None, resource_root=None, run_dir=None):
    """Edit only the generated copy, keeping all TOML strings properly escaped."""
    # Replace all floppy mounts with one drive-A runtime copy (first table wins).
    text = re.sub(r'^[ \t]*\[\[emulator\.media\.floppy\]\][^\n]*\n.*?(?=^[ \t]*\[|\Z)',
                  '', text, flags=re.M | re.S)
    text += '\n[[emulator.media.floppy]]\ndrive = 0\nfilename = '+json.dumps(Path(disk).as_posix())+'\n'
    def section(name, values, required=True):
        nonlocal text
        pattern = r'^[ \t]*\['+re.escape(name)+r'\][^\n]*\n.*?(?=^[ \t]*\[|\Z)'
        def edit(match):
            block = match.group(0)
            for key, value in values.items():
                line = key+' = '+value+'\n'
                match_key = re.search(r'^[ \t]*'+re.escape(key)+r'[ \t]*=', block, flags=re.M)
                if match_key:
                    # Arrays and inline tables can span several physical lines.
                    end = match_key.end()
                    for part in block[end:].splitlines(keepends=True):
                        end += len(part)
                        try:
                            tomllib.loads('value = '+block[match_key.end():end])
                        except tomllib.TOMLDecodeError:
                            continue
                        block = block[:match_key.start()]+line+block[end:]
                        break
                    else:
                        raise ValueError(f'Invalid MartyPC value: {name}.{key}')
                else:
                    block = block.rstrip()+'\n'+line
            return block
        text, count = re.subn(pattern, edit, text, flags=re.M | re.S)
        if not count:
            if required:
                raise ValueError(f'Missing MartyPC configuration section: {name}')
            text += '\n['+name+']\n'+''.join(key+' = '+value+'\n' for key, value in values.items())
    section('emulator', {'cpu_autostart': 'true'})
    section('emulator.scaler_preset.renderer', {'composite': str(bool(composite)).lower()})
    if resource_root is not None and run_dir is not None:
        parsed = tomllib.loads(text)
        base = Path(parsed['emulator'].get('basedir', '.'))
        if not base.is_absolute():
            base = Path(resource_root)/base
        paths = parsed['emulator'].get('paths', [])
        writable = {'dump', 'trace', 'screenshot', 'autofloppy', 'file_transfer'}
        for entry in paths:
            if entry.get('resource') in writable:
                entry['path'] = (Path(run_dir)/entry['resource']).as_posix()
                entry['create'] = True
            elif 'path' in entry:
                resolved = Path(entry['path'].replace('$basedir$', base.resolve().as_posix()))
                if not resolved.is_absolute():
                    resolved = Path(resource_root)/resolved
                entry['path'] = resolved.resolve().as_posix()
        # Support both inline path arrays and [[emulator.paths]] tables.
        text = re.sub(r'^[ \t]*\[\[emulator\.paths\]\][^\n]*\n.*?(?=^[ \t]*\[|\Z)',
                      '', text, flags=re.M | re.S)
        path_text = '['+', '.join('{'+', '.join(key+' = '+json.dumps(value)
                     for key, value in entry.items())+'}' for entry in paths)+']'
        section('emulator', {'basedir': json.dumps(base.resolve().as_posix()), 'paths': path_text})
    if floppy_type is not None:
        if floppy_type not in ('360k', '720k'):
            raise ValueError('Studio supports bootable 360 KB or 720 KB floppy images.')
        parsed = tomllib.loads(text)
        overlays = parsed.get('machine', {}).get('config_overlays', [])
        # Last overlay wins; retain other devices and the user's drive B.
        overlays = [value for value in overlays
                    if not re.fullmatch(r'floppy_[^:]+:0', value)]
        overlays.append(f'floppy_{floppy_type}:0')
        section('machine', {'config_overlays': json.dumps(overlays)})
        # Generated raster programs require the normal 8088 bus/timer model.
        section('machine', {'turbo': 'false', 'pit_phase': '0', 'patch_roms': 'false'})
        section('machine.cpu', {'dram_refresh_simulation': 'true', 'wait_states': 'true'}, required=False)
        section('emulator', {'title_hacks': 'false'})
    parsed = tomllib.loads(text)
    assert len(parsed['emulator']['media']['floppy']) == 1
    return text


def launch(link, disk, composite, *, run_root=None):
    link = validate_link(**link)
    disk = Path(disk).resolve()
    # Geometry must match the emulated drive under Marty's strict mounting.
    floppy_type = {360*1024: '360k', 720*1024: '720k'}.get(disk.stat().st_size)
    if floppy_type is None:
        raise ValueError('Expected a bootable 360 KB or 720 KB DOS floppy image.')
    run = create_run_dir() if run_root is None else create_run_dir(run_root)
    # Protect the user's saved master disk from emulator writes.
    runtime_disk = run/'preview.dsk'
    shutil.copyfile(disk, runtime_disk)
    config = Path(link['config'])
    generated = run/'martypc.toml'
    generated.write_text(launch_config(config.read_text(encoding='utf-8-sig'), runtime_disk, composite,
                                      floppy_type=floppy_type, resource_root=config.parent,
                                      run_dir=run), encoding='utf-8')
    log = run/'launch.log'
    with log.open('wb') as output:
        process = subprocess.Popen([link['executable'], '--configfile', str(generated)],
            cwd=run, stdout=output, stderr=subprocess.STDOUT)
    return process, log
