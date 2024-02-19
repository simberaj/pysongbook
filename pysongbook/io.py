import abc
from abc import ABC
import re
from typing import Generator, Type

from pysongbook.model import (
    Annotation,
    AuthorAnnotation,
    Chord,
    ChordedSegment,
    ChorusMark,
    CodaMark,
    EmptyStropheMark,
    GenericAnnotation,
    GenericChordModifier,
    LetteredStropheMark,
    NumberedStropheMark,
    PlainSegment,
    Song,
    Strophe,
    StropheMark,
    StropheSegment,
    TitleAnnotation,
)


class SongParseError(ValueError):
    pass


class SongFormat(ABC):
    @property
    @abc.abstractmethod
    def can_read(self) -> bool:
        ...

    @property
    @abc.abstractmethod
    def can_write(self) -> bool:
        ...


class ChordParser:
    tone_pattern = re.compile(r"[A-H](?:#|b)?")

    def parse(self, chord_str: str) -> Chord:
        if not chord_str:
            raise SongParseError("empty chord")
        root = self.tone_pattern.match(chord_str)
        if root is None:
            raise SongParseError(f"invalid chord major: {chord_str}")
        modifiers = []
        if chord_str[root.end() :]:
            modifiers.append(GenericChordModifier(chord_str[root.end() :]))
        return Chord(root.group(), modifiers=modifiers)


class DefaultFormat(SongFormat):
    can_read = True
    can_write = True

    # todo initialize this with config-level options
    default_heading_marker: str = " - "
    default_strophe_mark_delimiter: str = "."
    default_annotation_delimiter: str = ": "
    chord_start_mark: str = "["
    chord_end_mark: str = "]"

    chord_parser: ChordParser = ChordParser()
    part_separator_pattern: re.Pattern = re.compile(r"\n\s*\n")
    whitespace_normalizers: list[tuple[re.Pattern, str]] = [
        (re.compile(r"\s*\n\s*"), "\n"),  # remove all space around newlines
        (re.compile(r"[^\S\r\n]+"), " "),  # change all space except newline to a single space
    ]
    heading_markers: list[str] = [default_heading_marker, ": "]
    strophe_mark_delimiters: list[str] = [default_strophe_mark_delimiter, ":"]
    direct_strophe_marks: dict[str, Type[StropheMark]] = {
        "R": ChorusMark,
        "C": CodaMark,
    }  # todo resolve coda / c-strophe
    strophe_mark_patterns: list[tuple[re.Pattern, Type[StropheMark]]] = [
        (re.compile(r"\d+"), NumberedStropheMark),
        (re.compile(r"[A-E]+"), LetteredStropheMark),
    ]

    untitled_title: str = "<Untitled>"
    heading_indent: int = 8
    annotation_indent: int = 5

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
        return []  # TODO

    def _parse_strophe(self, part: str) -> Strophe:
        mark, body = self._parse_strophe_mark(part)
        pieces = self._normalize_strophe_whitespace(body).split(self.chord_start_mark)
        # todo non-implicit line chording settings, recognize repetitions
        segments: list[StropheSegment] = [PlainSegment(pieces[0])] if pieces[0] else []
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

    def _join_initial_plain_segments(self, items: list[Strophe | Annotation]) -> list[Strophe | Annotation]:
        # TODO the following would work if not for implicit chorus repetition; even then, better leave this to
        # TODO modifications within the model, not to parsing stage
        # strophes: list[tuple[int, Strophe]] = [(i, item) for i, item in enumerate(items) if isinstance(item, Strophe)]
        # for prev, current in zip(strophes[:-1], strophes[1:]):
        #     prev_i, prev_strophe = prev
        #     cur_i, cur_strophe = current
        #     if cur_strophe.segments and isinstance(cur_strophe.segments[0], PlainSegment):
        #         if prev_strophe.segments and
        return items

    def dumps(self, song: Song) -> str:
        header = f"\n{self._dump_heading_line(song)}\n\n"
        other_annots = self._dump_annotations(song)
        if other_annots:
            header += f"{other_annots}\n\n"
        body = "\n\n".join(self._dump_song_items(song))
        return header + body

    def _dump_heading_line(self, song: Song) -> str:
        authors = ", ".join(annot.name for annot in song.get_annotations_of_type(AuthorAnnotation))
        try:
            title = next(annot.title for annot in song.get_annotations_of_type(TitleAnnotation))
        except StopIteration:
            title = self.untitled_title
        if authors:
            return " " * self.heading_indent + authors + self.default_heading_marker + title
        else:
            return " " * self.heading_indent + title

    def _dump_annotations(self, song: Song) -> str:
        rem_annots = [annot for annot in song.annotations if not isinstance(annot, (AuthorAnnotation, TitleAnnotation))]
        if not rem_annots:
            return ""
        return "\n".join(self._dump_annotation(annot) for annot in rem_annots)

    def _dump_annotation(self, annot: Annotation) -> str:
        return " " * self.annotation_indent + annot.to_string(delimiter=self.default_annotation_delimiter)

    def _dump_song_items(self, song: Song) -> Generator[str, None, None]:
        strophe_indent = self._determine_strophe_indent(song)
        for item in song.items:
            if isinstance(item, Strophe):
                yield self._dump_strophe(item, indent=strophe_indent)
            else:
                yield self._dump_annotation(item)

    def _determine_strophe_indent(self, song: Song) -> int:
        return 4  # TODO, use min

    def _dump_strophe(self, strophe: Strophe, indent: int = 0) -> str:
        mark = strophe.mark.to_string(short=True)
        if mark:
            mark += self.default_strophe_mark_delimiter
        init = mark + " " * max(0, indent - len(mark))
        indenter = " " * indent
        raw_body = "".join(self._dump_segment(seg) for seg in strophe.segments)
        indented_body = init + raw_body.replace("\n", "\n" + indenter)
        print("IB", indented_body)
        return indented_body

    def _dump_segment(self, seg: StropheSegment) -> str:
        if isinstance(seg, ChordedSegment):
            return self.chord_start_mark + seg.chord.to_string() + self.chord_end_mark + seg.text
        else:
            return seg.text


if __name__ == "__main__":
    from pathlib import Path
    import pprint

    ahoj_slunko_path = Path(__file__).parent.parent / "test" / "data" / "ahoj_slunko.txt"
    with ahoj_slunko_path.open(encoding="utf8") as f:
        song = DefaultFormat().loads(f.read())
    pprint.pprint(song)
    print(DefaultFormat().dumps(song))
