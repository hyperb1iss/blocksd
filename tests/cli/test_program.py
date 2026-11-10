from blocksd.cli.program import _read_sources


def test_explicit_include_matches_collected_windows_file(tmp_path):
    main = tmp_path / "Main.littlefoot"
    helper = tmp_path / "Helpers.littlefoot"
    main.write_text('#include "Helpers.littlefoot"\nvoid repaint() { draw(); }')
    helper.write_bytes(b"\xef\xbb\xbfvoid draw() {}\r\n")

    _, includes = _read_sources(main, [helper])

    assert includes == {"Helpers.littlefoot": "void draw() {}\n"}
