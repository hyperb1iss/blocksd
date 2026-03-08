"""Tests for MIDI port name matching — no hardware required."""

from blocksd.topology.detector import _clean_port_name, _is_blocks_port


class TestBlocksPortDetection:
    def test_lightpad_block(self) -> None:
        assert _is_blocks_port("Lightpad BLOCK")

    def test_seaboard_block(self) -> None:
        assert _is_blocks_port("Seaboard Block")

    def test_lumi_keys_block(self) -> None:
        assert _is_blocks_port("LUMI Keys Block")

    def test_non_block_device(self) -> None:
        assert not _is_blocks_port("USB MIDI Interface")

    def test_non_block_with_block_substring(self) -> None:
        # "blocked" contains "block" but not as a word boundary
        assert not _is_blocks_port("blocked port")

    def test_empty_name(self) -> None:
        assert not _is_blocks_port("")


class TestPortNameCleaning:
    def test_strips_in_suffix(self) -> None:
        assert _clean_port_name("Lightpad BLOCK IN)") == "Lightpad BLOCK"

    def test_strips_out_suffix(self) -> None:
        assert _clean_port_name("Lightpad BLOCK OUT)") == "Lightpad BLOCK"

    def test_strips_index_suffix(self) -> None:
        assert _clean_port_name("Lightpad BLOCK [0]") == "Lightpad BLOCK"

    def test_preserves_clean_name(self) -> None:
        assert _clean_port_name("Lightpad BLOCK") == "Lightpad BLOCK"

    def test_strips_whitespace(self) -> None:
        assert _clean_port_name("  Lightpad BLOCK  ") == "Lightpad BLOCK"

    def test_input_output_match(self) -> None:
        """Input and output names should clean to the same base name."""
        cleaned_in = _clean_port_name("Lightpad BLOCK IN)")
        cleaned_out = _clean_port_name("Lightpad BLOCK OUT)")
        assert cleaned_in == cleaned_out
