import warnings
from pathlib import Path

from pysongbook.io import ModifiedSongsLatexChordParser, DefaultChordParser, ModifiedSongsLatexFormat

import pytest

chords_path = Path(__file__).parent / "data"

@pytest.fixture(scope="session")
def song_texts() -> list[str]:
    texts = [
        path.open(encoding="utf8").read()
        for path in chords_path.iterdir()
        if path.suffix == ".tex"
    ]
    return texts


def test_modif_songs_latex_parser(song_texts):
    format = ModifiedSongsLatexFormat()
    for text in song_texts:
        song = format.loads(text).normalized()
        format.dumps(song, chords=True)


@pytest.mark.parametrize("latex, normal", [
    (r"Hm\hidx{7}/F\shrp{}", "Hm7/F#"),
    (r"D\hidx{maj7}", "Dmaj7"),
    (r"D\shrp{}m\hidx{7/5b}", "D#m7/5b"),
    (r"A\hidx{sus2}", "Asus2"),
    (r"Hm", "Hm"),
    (r"C\didx{add9}", "Cadd9"),
])
def test_modif_songs_latex_chord_parser(latex, normal):
    assert ModifiedSongsLatexChordParser().parse(latex) == DefaultChordParser().parse(normal)
