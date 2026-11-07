import logging
from pathlib import Path
import sys

from pysongbook.format.core import SongFormat
from pysongbook.model import Song


def write_outputs(outputs: list[tuple[str, str]], output_path: Path | None) -> None:
    if len(outputs) == 1:
        single_pathname, single_output = outputs[0]
        if output_path is None:
            sys.stdout.write(single_output)
            return
        elif output_path.is_dir():
            output_path = output_path / single_pathname
        with output_path.open("w") as output_file:
            output_file.write(single_output)
    else:
        if output_path is None or not output_path.is_dir():
            raise ValueError(f"cannot write multiple songs to {output_path!r}")
        for pathname, output in outputs:
            output_path = output_path / pathname
            with output_path.open("w") as output_file:
                output_file.write(output)


def serialize_outputs(
    songs: list[tuple[str, Song]], parser_format: SongFormat, multi: bool, standalone: bool
) -> list[tuple[str, str]]:
    if not parser_format.can_write:
        raise ValueError(f"format {type(parser_format)!r} has no write capability")
    if multi and not parser_format.can_merge:
        raise ValueError(f"format {type(parser_format)!r} cannot merge songs into multisong files")
    outputs = []
    for pathname, song in songs:
        logging.debug("Serializing %s", pathname)
        outputs.append((pathname, parser_format.dumps(song)))
    if multi:
        outputs = [("merged", parser_format.merge([song_text for pathname, song_text in outputs]))]
    if standalone:
        outputs = [(pathname, parser_format.make_standalone(song_text)) for pathname, song_text in outputs]
    return outputs
