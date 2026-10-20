"""Repeat-cycle RGB previews must survive COM, ASM, disk, and Marty export."""

import subprocess
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image
import pytest

import cga_v167 as cga
import marty_link
from test_asm_export import find_nasm
from test_open_marty import disk_file


MODE = "320x200 Mode Switch Repeat"


@pytest.fixture(scope="module")
def prepared_app():
    app = cga.CgaConverterApp()
    app.withdraw()

    def prepare(count=3, tweaked="off", background=None):
        app.ms_switches_var.set("8")  # Remembered original-mode controls are irrelevant.
        app.ms_force_unique_palette_var.set(True)
        app.mode_var.set(MODE)
        app.on_mode_changed()
        app.ms_repeat_rows_var.set(str(count))
        app.tweaked_mode_var.set(tweaked)
        app.ms_repeat_background_var.set("Adjustable" if background is None else cga.CGA_COLOR_NAMES[background])
        app.dither_family_var.set("None")
        app.target_video_var.set("CGA")
        cycle = []
        background_choices = (0, 1, 6, 8, 9, 15)
        for slot in range(count):
            bg = background_choices[slot] if background is None else background
            pool = cga._repeat_mode_switch_palettes(bg, tweaked)
            # Each slot uses a distinct foreground triple; backgrounds are independent.
            cycle.append(pool[slot % len(pool)])
        palettes = [cycle[y % count] for y in range(200)]
        pixels = np.empty((200, 320, 3), np.uint8)
        for y, palette in enumerate(palettes):
            pixels[y] = np.asarray(palette, np.uint8)[(np.arange(320) + y) % 4]
        app.src_image = Image.fromarray(pixels)
        app.output_pimage = Image.fromarray(pixels)
        app.last_output_mode = MODE
        app.ms_seg_n = 1
        app.ms_pals_by_y = palettes
        app.ms_lockstep_max_plan = {"kind": "must-not-be-used-by-repeat"}
        app._valid_output_signature = app._output_settings_signature()
        return app, cycle

    yield prepare
    app.destroy()


def expected_com(app):
    indices = cga.derive_indices_320_from_rgb(app.output_pimage, app.ms_pals_by_y)
    return cga.build_com_320_mode_switch_n1(
        cga.pack_cga_320_vram_from_indices(indices),
        cga.build_cga_reg_table(app.ms_pals_by_y), exit_on_keypress=True,
        keep_border_black=bool(app.ms_black_border_var.get()))


@pytest.mark.parametrize('mode', [MODE, '320x200 (4 Colors) Mode Switch'])
def test_border_toggle_changes_export_without_reencoding(prepared_app, tmp_path, mode):
    app,cycle=prepared_app(2,'off',0)
    app.mode_var.set(mode)
    app.on_mode_changed()
    app.ms_switches_var.set('1')
    app.last_output_mode=mode
    app._valid_output_signature=app._output_settings_signature()
    original=app._output_settings_signature()
    binaries=[]
    for enabled in (False,True):
        app.ms_black_border_var.set(enabled)
        assert app._output_settings_signature()==original
        destination=tmp_path/f'border-{enabled}.com'
        with patch.object(cga.filedialog,'asksaveasfilename',return_value=str(destination)), \
                patch.object(cga.messagebox,'showerror') as error, \
                patch.object(cga.messagebox,'showinfo'), \
                patch.object(app,'on_convert',side_effect=AssertionError('No reconversion required')):
            app.on_export_com()
        error.assert_not_called()
        binaries.append(destination.read_bytes())
        assert_com_cycle_and_pixels(binaries[-1],app,cycle)
    assert binaries[0]!=binaries[1]
    assert binaries[1][0xE00:0xE08]==b'N1BRD001'


def assert_com_cycle_and_pixels(binary, app, cycle):
    tweaked_foregrounds = {
        frozenset(cga.CGA_COLORS[i] for i in indices)
        for indices in ((3, 4, 7), (11, 12, 15))
    }
    expected_modes = [0x0E if frozenset(map(tuple, palette[1:])) in tweaked_foregrounds else 0x0A
                      for palette in cycle]
    mixed = len(set(expected_modes)) > 1
    bios_mode = 5 if not mixed and expected_modes[0] == 0x0E else 4
    if binary[0xE00:0xE08] == b'N1BRD001':
        from cga_n1_border import descriptor
        descriptor(binary)
    else:
        assert binary[2:7] == bytes((0xB8, bios_mode, 0, 0xCD, 0x10))
    if mixed:
        mode_registers, color_registers = binary[-400::2], binary[-399::2]
        vram = np.frombuffer(binary[-16784:-400], np.uint8)
    else:
        mode_registers = bytes([expected_modes[0]]) * 200
        color_registers = binary[-200:]
        vram = np.frombuffer(binary[-16584:-200], np.uint8)
    decoded = np.empty((200, 320, 3), np.uint8)
    for y, register in enumerate(color_registers):
        mode = mode_registers[y]
        assert mode == expected_modes[y % len(cycle)]
        foreground = (3, 4, 7) if mode & 4 else ((3, 5, 7) if register & 0x20 else (2, 4, 6))
        bright = 8 if register & 0x10 else 0
        palette = [cga.CGA_COLORS[register & 15]] + [cga.CGA_COLORS[i + bright] for i in foreground]
        assert tuple(palette) == tuple(cycle[y % len(cycle)])
        assert register == color_registers[y % len(cycle)]
        offset = (y & 1) * 8192 + (y // 2) * 80
        indices = ((vram[offset:offset + 80, None] >> np.array([6, 4, 2, 0])) & 3).reshape(320)
        decoded[y] = np.asarray(palette)[indices]
    np.testing.assert_array_equal(decoded, np.asarray(app.output_pimage))


@pytest.mark.parametrize("count,tweaked,background", [
    (2, "on", 0), (3, "off", None), (4, "off", 0), (5, "on", None), (6, "on", None),
])
def test_com_export_preserves_every_cycle_slot_and_background(
        prepared_app, tmp_path, count, tweaked, background):
    app, cycle = prepared_app(count, tweaked, background)
    destination = tmp_path / "repeat.com"
    with patch.object(cga.filedialog, "asksaveasfilename", return_value=str(destination)) as save, \
            patch.object(cga.messagebox, "showinfo"), patch.object(cga.messagebox, "showerror") as error, \
            patch.object(cga, "build_com_320_mode_switch_lockstep_max", side_effect=AssertionError("dense route")):
        app.on_export_com()
    error.assert_not_called()
    assert save.call_args.kwargs["initialfile"] == f"cga_320_repeat{count}.com"
    binary = destination.read_bytes()
    assert binary == expected_com(app)
    assert_com_cycle_and_pixels(binary, app, cycle)


def test_repeat_asm_roundtrips_to_the_same_com(prepared_app, tmp_path):
    nasm = find_nasm()
    if not nasm:
        pytest.skip("NASM unavailable")
    app, cycle = prepared_app(6, "on", None)
    destination = tmp_path / "repeat.asm"
    with patch.object(cga.filedialog, "asksaveasfilename", return_value=str(destination)), \
            patch.object(cga.messagebox, "showinfo"), patch.object(cga.messagebox, "showerror") as error:
        app.on_export_asm()
    error.assert_not_called()
    rebuilt = tmp_path / "rebuilt.com"
    subprocess.run([nasm, "-f", "bin", "-O0", str(destination), "-o", str(rebuilt)],
                   check=True, capture_output=True, timeout=30)
    assert rebuilt.read_bytes() == expected_com(app)
    assert_com_cycle_and_pixels(rebuilt.read_bytes(), app, cycle)


def test_repeat_boot_disk_contains_the_same_com(prepared_app, tmp_path):
    app, cycle = prepared_app(6, "on", None)
    destination = tmp_path / "repeat.dsk"
    with patch.object(cga.filedialog, "asksaveasfilename", return_value=str(destination)), \
            patch.object(cga.messagebox, "showinfo"), patch.object(cga.messagebox, "showerror") as error:
        app.on_export_dsk()
    error.assert_not_called()
    image = destination.read_bytes()
    assert image[510:512] == b"\x55\xaa"
    binary = disk_file(image, "TEST.COM")
    assert binary == expected_com(app)
    assert_com_cycle_and_pixels(binary, app, cycle)


def test_repeat_open_marty_uses_rgb_and_autoruns_cached_bytes(prepared_app, tmp_path):
    app, cycle = prepared_app(5, "on", None)
    link = {"executable": "martypc.exe", "config": "martypc.toml"}
    process = Mock()
    process.poll.return_value = None
    with patch.object(marty_link, "resolve_link", return_value=link), \
            patch.object(marty_link, "create_run_dir", return_value=tmp_path), \
            patch.object(marty_link, "launch", return_value=(process, tmp_path / "launch.log")) as launch, \
            patch.object(cga.filedialog, "asksaveasfilename") as save, \
            patch.object(cga.messagebox, "showerror") as error, \
            patch.object(app, "after"), patch.object(app, "on_convert", side_effect=AssertionError("re-encode")):
        app.on_open_marty()
    error.assert_not_called()
    save.assert_not_called()
    destination = tmp_path / "preview.dsk"
    launch.assert_called_once_with(link, destination, False)
    image = destination.read_bytes()
    assert disk_file(image, "AUTOEXEC.BAT").endswith(b"TEST\r\n")
    binary = disk_file(image, "TEST.COM")
    assert binary == expected_com(app)
    assert_com_cycle_and_pixels(binary, app, cycle)


def test_repeat_export_rejects_a_background_that_breaks_the_cycle(prepared_app, tmp_path):
    app, _ = prepared_app(3, "off", None)
    rows = list(app.ms_pals_by_y)
    changed = list(rows[7])
    changed[0] = cga.CGA_COLORS[15]
    rows[7] = changed
    app.ms_pals_by_y = rows
    destination = tmp_path / "invalid.com"
    with patch.object(cga.messagebox, "showinfo") as info, \
            patch.object(cga.messagebox, "showerror") as error, \
            patch.object(cga.filedialog, "asksaveasfilename") as save:
        app.on_export_com(output_path=destination)
    assert not destination.exists()
    assert info.called or error.called
    save.assert_not_called()


def test_force_black_export_rejects_a_nonblack_background_even_when_cyclic(prepared_app, tmp_path):
    app, _ = prepared_app(3, "off", 0)
    palettes = []
    for palette in app.ms_pals_by_y:
        altered = list(palette)
        altered[0] = cga.CGA_COLORS[6]
        palettes.append(altered)
    app.ms_pals_by_y = palettes
    destination = tmp_path / "invalid-background.com"
    with patch.object(cga.messagebox, "showinfo") as info, \
            patch.object(cga.messagebox, "showerror") as error:
        app.on_export_com(output_path=destination)
    assert not destination.exists()
    assert info.called or error.called


@pytest.mark.parametrize('background', range(16))
def test_every_named_fixed_background_survives_com_register_export(prepared_app, tmp_path, background):
    app, cycle = prepared_app(2, 'off', background)
    path = tmp_path / 'fixed.com'
    with patch.object(cga.messagebox, 'showinfo'), patch.object(cga.messagebox, 'showerror') as error:
        app.on_export_com(output_path=path)
    error.assert_not_called()
    assert_com_cycle_and_pixels(path.read_bytes(), app, cycle)


@pytest.mark.parametrize('backgrounds,valid', [
    ((0, 8, 0, 8), True), ((0, 8, 7), True),
    ((0, 8, 0), False),  # Internal edges differ, but the cycle wrap repeats black.
    ((0, 8, 8, 7), False),
])
def test_no_repeat_background_export_checks_every_edge_including_wrap(prepared_app, tmp_path, backgrounds, valid):
    app, cycle = prepared_app(len(backgrounds), 'off', None)
    cycle = [(cga.CGA_COLORS[bg], *palette[1:]) for bg, palette in zip(backgrounds, cycle)]
    app.ms_pals_by_y = [cycle[y % len(cycle)] for y in range(200)]
    pixels = np.empty((200, 320, 3), np.uint8)
    for y, palette in enumerate(app.ms_pals_by_y):
        pixels[y] = np.asarray(palette)[np.arange(320) % 4]
    app.output_pimage = Image.fromarray(pixels)
    app.ms_repeat_background_var.set('Forced No Repeats')
    app._valid_output_signature = app._output_settings_signature()
    path = tmp_path / 'neighbors.com'
    with patch.object(cga.messagebox, 'showinfo'), patch.object(cga.messagebox, 'showerror') as error:
        app.on_export_com(output_path=path)
    if valid:
        error.assert_not_called()
        assert_com_cycle_and_pixels(path.read_bytes(), app, cycle)
    else:
        assert not path.exists()
        assert 'adjacent' in str(error.call_args)


@pytest.mark.parametrize("count,tweaked,background", [
    (3, "on", 0), (6, "off", 0), (4, "off", None),
])
def test_repeat_export_rejects_duplicate_full_palettes_in_cyclic_cache(
        prepared_app, tmp_path, count, tweaked, background):
    app, cycle = prepared_app(count, tweaked, background)
    cycle[-1] = cycle[0]
    app.ms_pals_by_y = [cycle[y % count] for y in range(200)]
    destination = tmp_path / "duplicate-cycle.com"
    with patch.object(cga.messagebox, "showinfo"), \
            patch.object(cga.messagebox, "showerror") as error:
        app.on_export_com(output_path=destination)
    assert not destination.exists()
    error.assert_called_once()
    assert 'unique' in str(error.call_args).lower()


def test_repeat_export_rejects_different_registers_with_identical_color_sets(prepared_app, tmp_path):
    app, _ = prepared_app(2, "off", None)
    # Both backgrounds are already present among the same three foregrounds.
    cycle = [cga._single_line_mode_switch_palettes(background, "off")[0]
             for background in (3, 5)]
    assert cycle[0] != cycle[1]
    assert set(map(tuple, cycle[0])) == set(map(tuple, cycle[1]))
    app.ms_pals_by_y = [cycle[y % 2] for y in range(200)]
    destination = tmp_path / "same-visible-colors.com"
    with patch.object(cga.messagebox, "showinfo"), \
            patch.object(cga.messagebox, "showerror") as error:
        app.on_export_com(output_path=destination)
    assert not destination.exists()
    error.assert_called_once()
    assert 'unique' in str(error.call_args).lower()


def test_repeat_export_rejects_identical_foregrounds_with_different_backgrounds(prepared_app, tmp_path):
    app, _ = prepared_app(2, "off", None)
    cycle = [cga._single_line_mode_switch_palettes(background, "off")[0]
             for background in (0, 1)]
    assert cycle[0][0] != cycle[1][0]
    assert cycle[0][1:] == cycle[1][1:]
    app.ms_pals_by_y = [cycle[y % 2] for y in range(200)]
    destination = tmp_path / "same-foreground-colors.com"
    with patch.object(cga.messagebox, "showinfo"), \
            patch.object(cga.messagebox, "showerror") as error:
        app.on_export_com(output_path=destination)
    assert not destination.exists()
    error.assert_called_once()
    assert 'foreground' in str(error.call_args).lower()


@pytest.mark.parametrize("setting,value", [
    ("ms_repeat_rows_var", "4"), ("ms_repeat_background_var", "Black"),
    ("ms_repeat_background_var", "Forced No Repeats"),
    ("ms_repeat_background_var", "Yellow"),
])
def test_changed_repeat_setting_blocks_all_exports_and_marty(prepared_app, tmp_path, setting, value):
    app, _ = prepared_app(3, "off", None)
    getattr(app, setting).set(value)
    with patch.object(cga.filedialog, "asksaveasfilename") as save, \
            patch.object(marty_link, "resolve_link") as resolve, \
            patch.object(cga.messagebox, "showinfo"):
        for action in (app.on_save, app.on_export_com, app.on_export_asm,
                       app.on_export_dsk, app.on_open_marty):
            action()
    save.assert_not_called()
    resolve.assert_not_called()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("background", [None, 0])
def test_disabling_tweaked_clamps_cycle_and_invalidates_all_exports(prepared_app, tmp_path, background):
    app, _ = prepared_app(6, "on", background)
    app.tweaked_off_rb.invoke()
    assert app.ms_repeat_rows_var.get() == "4"
    assert "changed from 6 to 4" in app.ms_repeat_limit_var.get()
    with patch.object(cga.filedialog, "asksaveasfilename") as save, \
            patch.object(marty_link, "resolve_link") as resolve, \
            patch.object(cga.messagebox, "showinfo"):
        for action in (app.on_save, app.on_export_com, app.on_export_asm,
                       app.on_export_dsk, app.on_open_marty):
            action()
    save.assert_not_called()
    resolve.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_hidden_original_mode_controls_do_not_invalidate_repeat_output(prepared_app):
    app, _ = prepared_app(3, "off", None)
    original = app._output_settings_signature()
    app.ms_switches_var.set("8 staggered")
    app.ms_force_unique_palette_var.set(not app.ms_force_unique_palette_var.get())
    app.ms_dither_aware_var.set(not app.ms_dither_aware_var.get())
    app.bg_color_var.set("Cyan" if app.bg_color_var.get() != "Cyan" else "Brown")
    assert app._output_settings_signature() == original
    assert app._require_current_output()


@pytest.mark.parametrize("count,tweaked,background", [(3, "off", None), (2, "on", 0), (6, "on", None)])
def test_real_repeat_conversion_matches_independent_com_decode(
        prepared_app, tmp_path, count, tweaked, background):
    app, _ = prepared_app(count, tweaked, background)
    y, x = np.indices((200, 320))
    source = Image.fromarray(np.stack(((x * 3 + y) % 256,
        (y * 7 + x // 3) % 256, (x + y * 2) % 256), axis=-1).astype(np.uint8))
    output, palettes, diagnostics = cga.quantize_320x200_mode_switch_repeat(
        source, count, forced_bg_idx=background, tweaked_mode=tweaked,
        dither_family="None", return_diagnostics=True)
    assert diagnostics["repeat_rows"] == count
    assert len(diagnostics["selected_cycle"]) == count
    assert diagnostics["global_optimum_certified"] is False
    assert output.size == (320, 200)
    assert len(palettes) == 200
    if background is not None:
        assert all(tuple(palette[0]) == cga.CGA_COLORS[background] for palette in palettes)
    assert len({frozenset(map(tuple, palette[1:])) for palette in palettes[:count]}) == count
    app.output_pimage, app.ms_pals_by_y = output, palettes
    destination = tmp_path / "real.com"
    with patch.object(cga.messagebox, "showinfo"), patch.object(cga.messagebox, "showerror") as error:
        app.on_export_com(output_path=destination)
    error.assert_not_called()
    assert_com_cycle_and_pixels(destination.read_bytes(), app, palettes[:count])
