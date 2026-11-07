import logging
from pathlib import Path
import sys

from pysongbook.format.core import SongFormat
import pysongbook.model


def get_inputs(input_path: Path | None, encoding: str) -> list[tuple[str, str]]:
    if input_path is None:
        inputs = [("stdin", sys.stdin.read())]
    elif input_path.is_dir():
        inputs = [
            (str(fpath), fpath.open(encoding=encoding).read()) for fpath in input_path.iterdir() if fpath.is_file()
        ]
    else:
        inputs = [(str(input_path), input_path.open(encoding=encoding).read())]
    return inputs


def parse_inputs(inputs: list[tuple[str, str]], parser_format: SongFormat) -> list[pysongbook.model.Song]:
    if not parser_format.can_read:
        raise ValueError(f"format {type(parser_format)!r} has no read capability")
    songs = []
    for pathname, inp in inputs:
        logging.info("Parsing %s", pathname)
        songs.append(parser_format.loads(inp))
    return songs
