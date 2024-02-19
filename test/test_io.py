from pathlib import Path


# import pytest

ahoj_slunko_path = Path(__file__).parent / "data" / "ahoj_slunko.txt"

# TODO install pytest
# @pytest.fixture(scope="session")
# def ahoj_slunko_text():
#     with ahoj_slunko_path.open() as f:
#         return f.read()

with ahoj_slunko_path.open() as f:
    ahoj_slunko_text = f.read()
