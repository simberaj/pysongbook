from pathlib import Path
import warnings

import pytest

from pysongbook.format import DefaultChordParser, ModifiedSongsLatexChordParser, ModifiedSongsLatexFormat


inputs_path = Path(__file__).parent / "data"
expected_outputs_path = Path(__file__).parent / "expected_out"


def _read_texs_folder(path: Path) -> dict[str, str]:
    return {p.stem: p.open(encoding="utf8").read() for p in path.iterdir() if p.suffix == ".tex"}


@pytest.fixture(scope="session")
def input_texs() -> dict[str, str]:
    return _read_texs_folder(inputs_path)


@pytest.fixture(scope="session")
def expected_output_texs() -> dict[str, str]:
    return _read_texs_folder(expected_outputs_path)


def test_modif_songs_latex_parser(input_texs: dict[str, str], expected_output_texs: dict[str, str]):
    format = ModifiedSongsLatexFormat()
    for name, text in input_texs.items():
        song = format.loads(text).normalized()
        result = format.dumps(song, chords=True)
        if name in expected_output_texs:
            assert result.strip() == expected_output_texs[name].strip()


@pytest.mark.parametrize(
    "latex, normal",
    [
        (r"Hm\hidx{7}/F\shrp{}", "Hm7/F#"),
        (r"D\hidx{maj7}", "Dmaj7"),
        (r"D\shrp{}m\hidx{7/5b}", "D#m7/5b"),
        (r"A\hidx{sus2}", "Asus2"),
        (r"Hm", "Hm"),
        (r"C\didx{add9}", "Cadd9"),
    ],
)
def test_modif_songs_latex_chord_parser(latex: str, normal: str):
    assert ModifiedSongsLatexChordParser().parse(latex) == DefaultChordParser().parse(normal)
