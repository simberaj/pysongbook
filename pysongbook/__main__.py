import argparse
import locale
import logging
from pathlib import Path

from pysongbook.format.agama import AgamaFormat
from pysongbook.format.bracket import BracketFormat
from pysongbook.format.core import ModelDictFormat
from pysongbook.format.modif_songs_latex import ModifiedSongsLaTeXFormat
from pysongbook.input import get_inputs, parse_inputs
from pysongbook.modify import NORMALIZER
from pysongbook.output import serialize_outputs, write_outputs


locale.setlocale(locale.LC_ALL, "")

FORMATS = [BracketFormat, AgamaFormat, ModifiedSongsLaTeXFormat, ModelDictFormat]

formats_by_name = {f.name: f for f in FORMATS} | {on: f for f in FORMATS for on in f.other_names}

parser = argparse.ArgumentParser(
    description="Process and convert songbook files",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    epilog="Available formats: " + ", ".join(f.name + " (" + ", ".join(f.other_names) + ")" for f in FORMATS),
)
parser.add_argument(
    "input", type=Path, default=None, nargs="?", help="songbook file or folder to process, default uses stdin"
)
parser.add_argument(
    "output", type=Path, default=None, nargs="?", help="songbook file or folder to output into, default uses stdout"
)
parser.add_argument("-f", "--in-format", default="bracket", help="songbook format to expect on input")
parser.add_argument("-F", "--out-format", default="bracket", help="songbook format to produce on output")
parser.add_argument("-m", "--in-multisong", action="store_true", help="input file(s) contain multiple songs")
parser.add_argument("-M", "--out-multisong", action="store_true", help="output file(s) contain multiple songs")
parser.add_argument(
    "-S", "--out-non-standalone", action="store_true", help="do not output standalone presentable file(s)"
)
parser.add_argument("-p", "--in-param", action="append", nargs=2, help="parameters to the input format parser")
parser.add_argument("-P", "--out-param", action="append", nargs=2, help="parameters to the output format serializer")
parser.add_argument("-c", "--encoding", default="utf8", help="input file(s) encoding")
parser.add_argument("-N", "--no-normalize", action="store_true", help="do not normalize song representations")


if __name__ == "__main__":
    args = parser.parse_args()
    logging.debug("Creating parser format %s", args.in_format)
    parser_format = formats_by_name[args.in_format](**dict(args.in_param or []))
    logging.debug("Creating output format %s", args.out_format)
    output_format = formats_by_name[args.out_format](**dict(args.out_param or []))
    logging.debug("Reading input files")
    all_inputs = get_inputs(args.input, encoding=args.encoding)
    logging.debug("Parsing input files")
    # TODO handle multi-song files
    parsed = parse_inputs(all_inputs, parser_format, multi=args.in_multisong)
    if not args.no_normalize:
        logging.debug("Normalizing song representations")
        normalized = [(pathname, NORMALIZER.modify(song)) for pathname, song in parsed]
    else:
        normalized = parsed
    logging.debug("Serializing output")
    serialized = serialize_outputs(
        normalized, output_format, multi=args.out_multisong, standalone=not args.out_non_standalone
    )
    logging.debug("Writing output")
    write_outputs(serialized, args.output)
