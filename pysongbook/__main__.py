import argparse
import logging
from pathlib import Path

from pysongbook.format.agama import AgamaFormat
from pysongbook.format.bracket import BracketFormat
from pysongbook.format.core import ModelDictFormat
from pysongbook.format.modif_songs_latex import ModifiedSongsLaTeXFormat
from pysongbook.input import get_inputs, parse_inputs
from pysongbook.modify import NORMALIZER


FORMATS = [BracketFormat, AgamaFormat, ModifiedSongsLaTeXFormat]

formats_by_name = {f.name: f for f in FORMATS}

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("input", type=Path, default=None, help="songbook file or folder to process, default uses stdin")
parser.add_argument(
    "output", type=Path, default=None, help="songbook file or folder to output into, default uses stdout"
)
parser.add_argument("-f", "--in-format", default="default", help="songbook format to expect on input")
parser.add_argument("-F", "--out-format", default="default", help="songbook format to produce on output")
parser.add_argument("-p", "--in-param", action="append", nargs=2, help="parameters to the input format parser")
parser.add_argument("-P", "--out-param", action="append", nargs=2, help="parameters to the output format serializer")
parser.add_argument("-c", "--encoding", default="utf8", help="input file(s) encoding")
parser.add_argument("-N", "--no-normalize", action="store_true", help="do not normalize song representations")


if __name__ == "__main__":
    args = parser.parse_args()
    logging.info("Creating parser format %s", args.in_format)
    parser_format = formats_by_name[args.in_format](**dict(args.in_param or []))
    logging.info("Creating output format %s", args.out_format)
    output_format = formats_by_name[args.out_format](**dict(args.out_param or []))
    all_inputs = get_inputs(args.input, encoding=args.encoding)
    # TODO handle multi-song files
    parsed = parse_inputs(all_inputs, parser_format)
    if not args.no_normalize:
        logging.info("Normalizing song representations")
        normalized = [NORMALIZER.modify(song) for song in parsed]
    else:
        normalized = parsed
    # TODO proper output, including merging
    for song in normalized:
        print(ModelDictFormat().dumps(song))  # noqa: T201  # print intended
