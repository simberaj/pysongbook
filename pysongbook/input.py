import logging
import operator
from pathlib import Path
import sys

from pysongbook.format.core import SongFormat
from pysongbook.model import Song


def get_inputs(input_path: Path | None, encoding: str) -> list[tuple[str, str]]:
    if input_path is None:
        inputs = [("stdin", sys.stdin.read())]
    elif input_path.is_dir():
        inputs = [
            (str(fpath), fpath.open(encoding=encoding).read()) for fpath in input_path.iterdir() if fpath.is_file()
        ]
    else:
        inputs = [(str(input_path), input_path.open(encoding=encoding).read())]
    return sorted(inputs, key=operator.itemgetter(0))


def parse_inputs(inputs: list[tuple[str, str]], parser_format: SongFormat, multi: bool) -> list[tuple[str, Song]]:
    if not parser_format.can_read:
        raise ValueError(f"format {type(parser_format)!r} has no read capability")
    if multi and not parser_format.can_split:
        raise ValueError(f"format {type(parser_format)!r} cannot split input multisong files")
    songs = []
    for pathname, inp in inputs:
        logging.debug("Parsing %s", pathname)
        songs.append((pathname, parser_format.loads(inp)))
    return songs
