import tempfile
from pathlib import Path
import tomllib
import unittest
from unittest.mock import patch

import marty_link as m


class MartyLinkTests(unittest.TestCase):
    def test_project_link_relocates_archive_but_preserves_custom_install(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            local = {'executable': 'current/martypc.exe', 'config': 'current/cga.toml'}
            with patch.object(m, 'settings_dir', return_value=root), patch.object(m, 'project_link', return_value=local):
                self.assertEqual(m.resolve_link(), local)
                m.save_link({'executable': 'C:/old/external/martypc/target/release/martypc.exe',
                             'config': 'C:/old/external/martypc/install/martypc-cga.toml'})
                before = (root/'marty-link.json').read_bytes()
                self.assertEqual(m.resolve_link(), local)
                self.assertEqual((root/'marty-link.json').read_bytes(), before)
                custom = {'executable': 'D:/custom/martypc.exe', 'config': 'D:/custom/main.toml'}
                m.save_link(custom)
                with patch.object(m, 'validate_link', return_value=custom) as validate:
                    self.assertEqual(m.resolve_link(), custom)
                    validate.assert_called_once_with(**custom)
                with patch.object(m, 'project_link', side_effect=ValueError('Broken local ROMs')) as discover, \
                        patch.object(m, 'validate_link', return_value=custom):
                    self.assertEqual(m.resolve_link(), custom)
                    discover.assert_not_called()

    def test_runtime_geometry_timing_and_multiline_overlay(self):
        text = '''[meta]
config_version = "0.5"
[machine]
config_name = "my-machine"
config_overlays = [
  "floppy_360k:0",
  "floppy_360k:1",
  "other_device",
]
turbo = true
[emulator]
paths = [
  { resource = "rom", path = "$basedir$/roms", recurse = true },
  { resource = "screenshot", path = "$basedir$/screenshots", create = true },
]
[[emulator.scaler_preset]]
name = "default"
[emulator.scaler_preset.renderer]
composite = false
'''
        data = tomllib.loads(m.launch_config(text, Path('demo.dsk'), True, floppy_type='720k',
                                             resource_root=Path.cwd(), run_dir=Path.cwd()/'runtime'))
        self.assertEqual(data['machine']['config_overlays'], ['floppy_360k:1', 'other_device', 'floppy_720k:0'])
        self.assertFalse(data['machine']['turbo'])
        self.assertFalse(data['machine']['patch_roms'])
        self.assertTrue(data['machine']['cpu']['wait_states'])
        self.assertTrue(data['machine']['cpu']['dram_refresh_simulation'])
        self.assertFalse(data['emulator']['title_hacks'])
        self.assertEqual(data['emulator']['paths'][0]['path'], (Path.cwd()/'roms').as_posix())
        self.assertEqual(data['emulator']['paths'][1]['path'], (Path.cwd()/'runtime/screenshot').as_posix())

    def test_missing_local_install_returns_none_and_invalid_saved_link_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(m, 'settings_dir', return_value=root), patch.object(m, 'project_link', return_value=None):
                self.assertIsNone(m.resolve_link())
                (root/'marty-link.json').write_text('{invalid')
                with self.assertRaises(ValueError):
                    m.resolve_link()

    def test_config_preserves_machine_and_selects_one_disk(self):
        text = '''[meta]
config_version = "0.5"
[machine]
config_name = "my-machine"
[emulator]
cpu_autostart = false
[[emulator.media.floppy]]
drive = 1
filename = "old.dsk"
[[emulator.scaler_preset]]
name = "default"
[emulator.scaler_preset.renderer]
composite = false
'''
        for composite in (False, True):
            data = tomllib.loads(m.launch_config(text, Path('disk with spaces.dsk'), composite))
            self.assertEqual(data['machine']['config_name'], 'my-machine')
            self.assertTrue(data['emulator']['cpu_autostart'])
            self.assertEqual(data['emulator']['media']['floppy'],
                             [{'drive': 0, 'filename': 'disk with spaces.dsk'}])
            self.assertEqual(data['emulator']['scaler_preset'][0]['renderer']['composite'], composite)

    def test_launch_protects_original_disk_and_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe = root/'martypc.exe'
            exe.touch()
            for name in ('machine', 'rom'):
                (root/name).mkdir()
                (root/name/'resource').touch()
            cfg = root/'main.toml'
            original = '''[meta]
config_version = "0.5"
[machine]
config_name = "my-machine"
[emulator]
basedir = "."
[[emulator.paths]]
resource = "machine"
path = "$basedir$/machine"
[[emulator.paths]]
resource = "rom"
path = "$basedir$/rom"
[[emulator.scaler_preset]]
name = "default"
[emulator.scaler_preset.renderer]
composite = false
'''
            cfg.write_text(original)
            disk = root/'master.dsk'
            disk.write_bytes(b'disk contents'.ljust(360*1024, b'\0'))
            link = m.validate_link(exe, cfg)
            with patch.object(m, 'settings_dir', return_value=root/'settings'), patch.object(m.subprocess, 'Popen') as popen:
                m.save_link(link)
                self.assertEqual(m.load_link(), link)
                _, log = m.launch(link, disk, True)
                generated = Path(popen.call_args.args[0][2])
                data = tomllib.loads(generated.read_text())
                runtime = Path(data['emulator']['media']['floppy'][0]['filename'])
                self.assertNotEqual(runtime, disk)
                self.assertEqual(runtime.read_bytes(), disk.read_bytes())
                self.assertEqual(popen.call_args.kwargs['cwd'], runtime.parent)
                self.assertTrue(log.exists())
                self.assertEqual(data['machine']['config_overlays'], ['floppy_360k:0'])
                self.assertEqual(data['emulator']['basedir'], root.resolve().as_posix())
            self.assertEqual(cfg.read_text(), original)
            self.assertEqual(disk.read_bytes(), b'disk contents'.ljust(360*1024, b'\0'))
