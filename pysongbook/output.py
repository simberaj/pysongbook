import logging
from pathlib import Path
import sys

from pysongbook.format.core import SongFormat
from pysongbook.index import SongIndex
from pysongbook.model import Song


def write_outputs(outputs: dict[str | None, str], output_path: Path | None) -> None:
    if len(outputs) == 1:
        single_pathname, single_output = next(iter(outputs.items()))
        write_single_output(single_pathname, single_output, output_path)
    else:
        if output_path is None:
            raise ValueError(f"cannot write multiple songs to {output_path!r}")
        if not output_path.is_dir():
            output_path, primary_name = output_path.parent, output_path.name
            amended_outputs = outputs.copy()
            for pathname in outputs:
                if pathname is None:
                    amended_outputs[primary_name] = outputs[None]
                    amended_outputs.pop(None)
            outputs = amended_outputs
        for pathname, output in outputs.items():
            write_single_output(pathname, output, output_path)


def write_single_output(pathname: str | None, output: str, output_path: Path | None) -> None:
    if output_path is None:
        sys.stdout.write(output)
        return
    elif output_path.is_dir():
        if pathname is None:
            raise ValueError(f"cannot write song to directory {output_path!r} without pathname")
        output_path = output_path / pathname
    with output_path.open("w") as output_file:
        output_file.write(output)


def serialize_outputs(
    songs: list[tuple[str, Song]],
    song_format: SongFormat,
    indices: dict[str, SongIndex],
    multi: bool,
    standalone: bool,
    title_content: str | None,
) -> dict[str | None, str]:
    if not song_format.can_write:
        raise ValueError(f"format {type(song_format)!r} has no write capability")
    if multi and not song_format.can_merge:
        raise ValueError(f"format {type(song_format)!r} cannot merge songs into multisong files")
    outputs = {}
    for pathname, song in songs:
        logging.debug("Serializing %s", pathname)
        outputs[pathname] = song_format.dump_song(song)
    if multi:
        logging.debug("Merging songs")
        merged_songs = song_format.merge_songs(outputs.values(), standalone=standalone)
        if standalone:
            index_outputs = {}
            for index_identifier, index in indices.items():
                logging.debug("Serializing index %s", index.title)
                dumped_contents = song_format.dump_index(index, index_identifier)
                for pathname, content in dumped_contents.items():
                    index_outputs[pathname] = (
                        song_format.merge_indices([index_outputs[pathname], content])
                        if pathname in index_outputs
                        else content
                    )
            index_content = index_outputs.pop(None, "")
            logging.debug("Assembling output")
            merged_content = song_format.make_standalone(merged_songs, index_content, title_content or "")
            return {None: merged_content} | index_outputs
        else:
            return {None: merged_songs}
    elif standalone:
        logging.debug("Converting to standalone format")
        outputs = {
            pathname: song_format.make_standalone(song_text, title_content=title_content or "")
            for pathname, song_text in outputs.items()
        }
    return outputs
