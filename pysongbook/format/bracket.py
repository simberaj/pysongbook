from collections.abc import Generator
import dataclasses
import re

from pysongbook.format.chord import TextChordParser
from pysongbook.format.core import SongFormat, SongParseError
from pysongbook.model import (
    Annotation,
    AuthorAnnotation,
    ChordedSegment,
    ChorusMark,
    EmptyStropheMark,
    LetteredStropheMark,
    NumberedStropheMark,
    Song,
    Strophe,
    StropheMark,
    StropheSegment,
    TitleAnnotation,
    UnchordedSegment,
)


@dataclasses.dataclass
class BracketFormat(SongFormat):
    name = "default"
    can_read = True
    can_write = True

    # todo initialize this with config-level options
    default_heading_marker: str = " - "
    default_strophe_mark_delimiter: str = "."
    default_annotation_delimiter: str = ": "
    chord_start_mark: str = "["
    chord_end_mark: str = "]"

    chord_parser: TextChordParser = dataclasses.field(default_factory=lambda: TextChordParser())
    part_separator_pattern: re.Pattern = re.compile(r"\n\s*\n")
    whitespace_normalizers: list[tuple[re.Pattern, str]] = dataclasses.field(
        default_factory=lambda: [
            (re.compile(r"\s*\n\s*"), "\n"),  # remove all space around newlines
            (re.compile(r"[^\S\r\n]+"), " "),  # change all space except newline to a single space
        ]
    )
    additional_heading_markers: list[str] = dataclasses.field(default_factory=lambda: [": "])
    additional_strophe_mark_delimiters: list[str] = dataclasses.field(default_factory=lambda: [":"])
    direct_strophe_marks: dict[str, type[StropheMark]] = dataclasses.field(
        default_factory=lambda: {
            "R": ChorusMark,
            # "C": CodaMark,  # coda recognition is done by normalization in the model
        }
    )
    strophe_mark_patterns: list[tuple[re.Pattern, type[StropheMark]]] = dataclasses.field(
        default_factory=lambda: [
            (re.compile(r"\d+"), NumberedStropheMark),
            (re.compile(r"[A-E]+"), LetteredStropheMark),
        ]
    )

    untitled_title: str = "<Untitled>"
    heading_indent: int = 8
    annotation_indent: int = 5

    def __post_init__(self):
        self.heading_markers: list[str] = [self.default_heading_marker, *self.additional_heading_markers]
        self.strophe_mark_delimiters: list[str] = [
            self.default_strophe_mark_delimiter,
            *self.additional_strophe_mark_delimiters,
        ]

    def loads(self, song_text: str) -> Song:
        parts = self._split_song_parts(song_text)
        init_annot_part_i = 0
        if "\n" not in parts[0]:
            annotations = self._try_parse_heading(parts[0])
            if annotations:
                init_annot_part_i = 1
        else:
            annotations = []
        if len(parts) <= init_annot_part_i:
            raise SongParseError("empty song: no song body found")
        init_annotations = self._try_parse_annotations(parts[init_annot_part_i])
        if init_annotations:
            annotations.extend(init_annotations)
            first_item_i = init_annot_part_i + 1
        else:
            first_item_i = init_annot_part_i
        items = []
        for part in parts[first_item_i:]:
            some_annotations = self._try_parse_annotations(part, initial=False)
            if some_annotations:
                items.extend(annotations)
            else:
                items.append(self._parse_strophe(part))
        return Song(annotations=annotations, items=items)

    def _split_song_parts(self, song_text: str) -> list[str]:
        return [
            part.rstrip().lstrip("\n")
            for part in self.part_separator_pattern.split(song_text)
            if part and not part.isspace()
        ]

    def _try_parse_heading(self, line: str) -> list[Annotation]:
        for marker in self.heading_markers:
            if marker in line:
                if line.count(marker) > 1:
                    continue
                author, title = line.strip().split(marker)
                return [AuthorAnnotation(author.strip()), TitleAnnotation(title.strip())]
        return []

    def _try_parse_annotations(self, part: str, initial: bool = True) -> list[Annotation]:
        del part, initial
        return []  # TODO

    def _parse_strophe(self, part: str) -> Strophe:
        mark, body = self._parse_strophe_mark(part)
        pieces = self._normalize_strophe_whitespace(body).split(self.chord_start_mark)
        segments: list[StropheSegment] = [UnchordedSegment(pieces[0])] if pieces[0] else []
        for piece in pieces[1:]:
            if self.chord_end_mark not in piece:
                raise SongParseError("mismatched chord start/end marks")  # todo better info on where it occurred
            chord_str, text_str = piece.split(self.chord_end_mark, maxsplit=1)
            segments.append(ChordedSegment(chord=self.chord_parser.parse(chord_str), text=text_str))
        return Strophe(mark=mark, segments=segments)

    def _parse_strophe_mark(self, part: str) -> tuple[StropheMark, str]:
        strip_part = part.strip()
        init, rest = strip_part.split(maxsplit=1)
        for delim in self.strophe_mark_delimiters:
            init = init.removesuffix(delim)
        direct_mark_type = self.direct_strophe_marks.get(init)
        if direct_mark_type is not None:
            return direct_mark_type.from_string(init), rest
        for mark_re, mark_type in self.strophe_mark_patterns:
            if mark_re.fullmatch(init):
                return mark_type.from_string(init), rest
        return EmptyStropheMark(), part

    def _normalize_strophe_whitespace(self, body: str) -> str:
        for pattern, repl in self.whitespace_normalizers:
            body = pattern.sub(repl, body)
        return body.strip()

    def dumps(self, song: Song, indent: int | None = None, chords: bool = True) -> str:
        header = f"\n{self.dump_heading(song)}\n\n"
        other_annots = self.dump_annotations(song, chords=chords)
        if other_annots:
            header += f"{other_annots}\n\n"
        body = "\n\n".join(self.dump_song_items(song, indent=indent, chords=chords))
        return header + body

    def dump_heading(self, song: Song) -> str:
        authors = ", ".join(annot.name for annot in song.get_annotations_of_type(AuthorAnnotation))
        title = song.get_title() or self.untitled_title
        if authors:
            return " " * self.heading_indent + authors + self.default_heading_marker + title
        else:
            return " " * self.heading_indent + title

    def dump_annotations(self, song: Song, chords: bool = True) -> str:
        rem_annots = song.get_displayable_annotations(chords=chords)
        if not rem_annots:
            return ""
        return "\n".join(self.dump_annotation(annot) for annot in rem_annots)

    def dump_annotation(self, annot: Annotation) -> str:
        return " " * self.annotation_indent + annot.to_string(delimiter=self.default_annotation_delimiter)

    def dump_song_items(self, song: Song, indent: int | None = None, chords: bool = True) -> Generator[str, None, None]:
        if indent is None:
            indent = self._determine_strophe_indent(song)
        for item in song.items:
            if isinstance(item, Strophe):
                yield self.dump_strophe(item, indent=indent, chords=chords)
            else:  # elif not is chord annotation if not chords
                yield self.dump_annotation(item)

    def _determine_strophe_indent(self, song: Song) -> int:
        mark_strs = [self.dump_strophe_mark(item.mark, indent=0) for item in song.items if isinstance(item, Strophe)]
        if not mark_strs:
            return 0
        mark_length = max(len(mark_str) for mark_str in mark_strs)
        return mark_length

    def dump_strophe(self, strophe: Strophe, indent: int = 0, chords: bool = True) -> str:
        init = self.dump_strophe_mark(strophe.mark, indent=indent)
        indenter = " " * indent
        raw_body = "".join(self.dump_segment(seg, chords=chords) for seg in strophe.single_line_segments())
        indented_body = init + raw_body.replace("\n", "\n" + indenter)
        return indented_body

    def dump_strophe_mark(self, mark: StropheMark, indent: int = 0):
        mark_str = mark.to_string(short=True)
        if mark_str:
            mark_str += self.default_strophe_mark_delimiter
        init = mark_str + " " * max(1, indent - len(mark_str))
        return init

    def dump_segment(self, seg: StropheSegment, chords: bool = True) -> str:
        if isinstance(seg, ChordedSegment) and chords:
            return self.chord_start_mark + seg.chord.to_string() + self.chord_end_mark + seg.text
        else:
            return seg.text
