"""Real compiler boundaries: includes, metadata, diagnostics, and packaging."""

import struct
import subprocess
from unittest.mock import patch

import pytest

from blocksd.littlefoot.compiler import compile_file, compile_source
from blocksd.littlefoot.source import collect_file_sources, prepare_source


def test_native_compiler_builds_valid_program():
    code = compile_source("void repaint() { fillPixel(0xff00ff00, 0, 0); }")
    checksum, size, functions, _globals, heap = struct.unpack_from("<5H", code)
    assert size == len(code)
    assert functions == 1
    assert heap == 512
    computed = size
    for byte in code[2:]:
        computed = (computed * 3 + byte) & 0xFFFF
    assert checksum == computed


def test_native_compiler_reports_unknown_function():
    with pytest.raises(ValueError, match="unknownNative"):
        compile_source("void repaint() { unknownNative(); }")


def test_error_line_number_without_metadata_matches_source():
    with pytest.raises(ValueError, match=r"Line 1, column "):
        compile_source("void repaint() { unknownNative(); }")


def test_native_compiler_includes_supplied_files():
    code = compile_source(
        '#include "lib/draw.littlefoot"\nvoid repaint() { draw(); }',
        includes={
            "lib/draw.littlefoot": '#include "colour.littlefoot"\nvoid draw() { fillPixel(colour, 0, 0); }',
            "lib/colour.littlefoot": "const int colour = 0xff0000ff;",
        },
    )
    assert len(code) > 10


def test_standard_library_is_available():
    assert compile_source(
        '#include "../LittleFootLibrary/ClusterSync.littlefoot"\n'
        "void ClusterSync_Overrride_clusterChanged() {}\n"
        "void initialise() { ClusterSync_initialise(); }"
    )


def test_missing_include_reports_name():
    with pytest.raises(ValueError, match=r"Include not supplied: missing\.littlefoot"):
        compile_source('#include "missing.littlefoot"\nvoid repaint() {}')


def test_include_cycle_is_rejected():
    with pytest.raises(ValueError, match="Circular"):
        prepare_source(
            '#include "a.littlefoot"', includes={"a.littlefoot": '#include "a.littlefoot"'}
        )


def test_comments_do_not_trigger_include_resolution():
    assert compile_source('// #include "/etc/passwd"\nvoid repaint() {}')


def test_native_compiler_cannot_resolve_files_even_if_preprocessor_misses_directive(tmp_path):
    secret = tmp_path / "secret.littlefoot"
    secret.write_text("const int secret = 123;")
    # The vendor parser accepts a directive after code on the same line, while
    # our supported include syntax requires a directive on its own line.
    with pytest.raises(ValueError, match="File not found"):
        compile_source(f'const int a = 0; #include "{secret}"\nvoid repaint() {{}}')


def test_dashboard_metadata_defaults():
    source = """/*<metadata><variables>
      <variable name="bpm" type="int" value="90" />
      <variable name="note" type="midiNote" value="C#3" />
      <variable name="active" type="bool" value="true" />
      <variable name="gain" type="float" value="0.5" />
    </variables></metadata>*/
    void repaint() { if (active) fillPixel(bpm + note + int(gain), 0, 0); }
    """
    prepared = prepare_source(source)
    assert "const int note = 61;" in prepared
    assert compile_source(source)


def test_metadata_rejects_code_injection():
    with pytest.raises(ValueError):
        prepare_source(
            '/*<metadata><variables><variable name="x" value="1; bad()" /></variables></metadata>*/'
        )


def test_only_referenced_local_files_are_read(tmp_path):
    source = tmp_path / "main.littlefoot"
    source.write_text('#include "color.littlefoot"\nvoid repaint() { fillPixel(color, 0, 0); }')
    (tmp_path / "color.littlefoot").write_text("const int color = 1;")
    (tmp_path / "unrelated.littlefoot").write_bytes(b"\xff")
    _, includes = collect_file_sources(source)
    assert list(includes) == ["color.littlefoot"]
    assert compile_file(source)


def test_local_symlink_cannot_escape_source_directory(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    outside = tmp_path / "outside.littlefoot"
    outside.write_text("const int secret = 1;")
    (source_dir / "secret.littlefoot").symlink_to(outside)
    source = source_dir / "main.littlefoot"
    source.write_text('#include "secret.littlefoot"\nvoid repaint() {}')
    with pytest.raises(ValueError, match="Include not supplied"):
        compile_file(source)


def test_compilation_timeout_is_actionable():
    with (
        patch(
            "blocksd.littlefoot.compiler.subprocess.run",
            side_effect=subprocess.TimeoutExpired("compiler", 15),
        ),
        pytest.raises(ValueError, match="exceeded 15 seconds"),
    ):
        compile_source("void repaint() {}")


def test_source_size_is_checked_before_invocation():
    with pytest.raises(ValueError, match="256 KiB"):
        compile_source(" " * 262_144 + "void repaint() {}")


def test_implicit_heap_keeps_global_arrays_after_the_sdk_default():
    code = compile_source("int notes[4]; void initialise() { setHeapByte(144, 1); notes[0] = 7; }")
    assert struct.unpack_from("<H", code, 8)[0] == 512 + 4 * 4


def test_explicit_heap_overrides_sdk_default():
    code = compile_source("#heapsize: 128\nvoid repaint() {}")
    assert struct.unpack_from("<H", code, 8)[0] == 128


def test_windows_source_and_nested_includes_with_bom():
    code = compile_source(
        '\ufeff#include "draw.littlefoot"\r\nvoid repaint() { draw(); }\r\n',
        includes={
            "draw.littlefoot": '\ufeff#include "colour.littlefoot"\r\nvoid draw() { fillPixel(colour, 0, 0); }\r\n',
            "colour.littlefoot": "\ufeffconst int colour = 0xff0000ff;\r\n",
        },
    )
    assert len(code) > 10


def test_deep_include_chain_does_not_use_python_recursion():
    includes = {
        f"{index}.littlefoot": f'#include "{index + 1}.littlefoot"\n' for index in range(1500)
    }
    includes["1500.littlefoot"] = "void repaint() {}"
    code = compile_source('#include "0.littlefoot"', includes=includes)
    assert len(code) > 10


def test_nested_include_bytes_are_counted_once():
    payload = "/*" + "x" * 140_000 + "*/\nvoid repaint() {}"
    prepared = prepare_source(
        '#include "outer.littlefoot"',
        includes={"outer.littlefoot": '#include "inner.littlefoot"', "inner.littlefoot": payload},
    )
    assert prepared == payload + "\n\n"


def test_unclosed_comment_cannot_activate_include():
    source = "/*x" * 80_000 + '\n#include "missing.littlefoot"'
    assert prepare_source(source) == source


def test_unclosed_metadata_is_reported_without_rescanning_openers():
    with pytest.raises(ValueError, match="Unterminated Dashboard metadata"):
        prepare_source("/*" + "<metadata>" * 25_000 + "*/")


def test_malformed_include_with_long_whitespace_is_left_for_compiler():
    source = '#include "missing.littlefoot"' + " " * 240_000 + "invalid"
    assert prepare_source(source) == source


@pytest.mark.parametrize("kind", ["colour", "option"])
def test_unsupported_metadata_type_is_reported(kind):
    with pytest.raises(ValueError, match=f"Unsupported Dashboard metadata type: {kind}"):
        prepare_source(
            f'/*<metadata><variables><variable name="x" type="{kind}" value="1" /></variables></metadata>*/'
        )


def test_unsupported_metadata_vector_is_reported():
    with pytest.raises(ValueError, match="Unsupported Dashboard metadata element: vector"):
        prepare_source('/*<metadata><variables><vector count="4" /></variables></metadata>*/')


def test_empty_metadata_with_quoted_angle_bracket_is_valid():
    assert compile_source('/*<metadata description="a > b"/>*/\nvoid repaint() {}')


def test_local_bom_source_collects_referenced_includes(tmp_path):
    source = tmp_path / "main.littlefoot"
    source.write_bytes(b'\xef\xbb\xbf#include "draw.littlefoot"\r\nvoid repaint() { draw(); }\r\n')
    (tmp_path / "draw.littlefoot").write_bytes(b"\xef\xbb\xbfvoid draw() {}\r\n")
    text, includes = collect_file_sources(source)
    assert text.startswith("#include")
    assert includes == {"draw.littlefoot": "void draw() {}\n"}
    assert compile_file(source)
