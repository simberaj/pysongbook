import argparse
import logging
import sys
from pathlib import Path

import pysongbook.io
import pysongbook.model

FORMATS = {}
for name in dir(pysongbook.io):
    val = getattr(pysongbook.io, name)
    if isinstance(val, type) and issubclass(val, pysongbook.io.SongFormat):
        FORMATS[val.name] = val


def get_inputs(input_path: Path | None, encoding: str) -> list[tuple[str, str]]:
    if input_path is None:
        inputs = [("stdin", sys.stdin.read())]
    elif input_path.is_dir():
        inputs = [(str(fpath), fpath.open(encoding=encoding).read()) for fpath in input_path.iterdir() if fpath.is_file()]
    else:
        inputs = [(str(input_path), input_path.open(encoding=encoding).read())]
    return inputs


def parse_inputs(inputs: list[tuple[str, str]], parser_format: pysongbook.io.SongFormat) -> list[pysongbook.model.Song]:
    if not parser_format.can_read:
        raise ValueError(f"format {type(parser_format)!r} has no read capability")
    songs = []
    for pathname, inp in inputs:
        logging.info("Parsing %s", pathname)
        songs.append(parser_format.loads(inp))
    return songs


parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("input", type=Path, default=None, help="songbook file or folder to process, default uses stdin")
parser.add_argument("output", type=Path, default=None, help="songbook file or folder to output into, default uses stdout")
parser.add_argument("-f", "--in-format", default="default", help="songbook format to expect on input")
parser.add_argument("-F", "--out-format", default="default", help="songbook format to produce on output")
parser.add_argument("-p", "--in-param", action="append", nargs=2, help="parameters to the input format parser")
parser.add_argument("-P", "--out-param", action="append", nargs=2, help="parameters to the output format serializer")
parser.add_argument("-c", "--encoding", default="utf8", help="input file(s) encoding")
parser.add_argument("-N", "--no-normalize", action="store_true", help="input file(s) encoding")


if __name__ == "__main__":
    args = parser.parse_args()
    logging.info("Creating parser format %s", args.in_format)
    parser_format = FORMATS[args.in_format](**dict(args.in_param or []))
    logging.info("Creating output format %s", args.out_format)
    output_format = FORMATS[args.out_format](**dict(args.out_param or []))
    all_inputs = get_inputs(args.input, encoding=args.encoding)
    # TODO handle multi-song files
    parsed = parse_inputs(all_inputs, parser_format)
    if not args.no_normalize:
        logging.info("Normalizing song representations")
        normalized = [song.normalized() for song in parsed]
    else:
        normalized = parsed
    # TODO proper output, including merging
    for song in normalized:
        print(pysongbook.io.ModelDictFormat().dumps(song))
