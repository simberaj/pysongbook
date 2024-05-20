from pathlib import Path

from pysongbook.io import ModifiedSongsLatexChordParser, DefaultChordParser

import pytest

# ahoj_slunko_path = Path(__file__).parent / "data" / "ahoj_slunko.txt"

# TODO install pytest
# @pytest.fixture(scope="session")
# def ahoj_slunko_text():
#     with ahoj_slunko_path.open() as f:
#         return f.read()

# with ahoj_slunko_path.open() as f:
#     ahoj_slunko_text = f.read()


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
