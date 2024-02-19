import abc
from abc import ABC
import re
from typing import Generator, Type, Callable

from pysongbook.model import (
    Annotation,
    AuthorAnnotation,
    Chord,
    ChordedSegment,
    ChorusMark,
    CodaMark,
    EmptyStropheMark,
    GenericChordModifier,
    LetteredStropheMark,
    NumberedStropheMark,
    PlainSegment,
    Song,
    Strophe,
    StropheMark,
    StropheSegment,
    TitleAnnotation, ChordModifier, MajorSeventh, Minor, Suspended, AddedNote, DominantSeventh, Altered, BassNote,
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


def _parse_altered_modifier_match(match: re.Match) -> Altered:
    print(match.group(), match.group(0), match.group(1), match.group(2))
    return Altered(
        direction=match.group(1),
        factor=(5 if not match.group(2) else int(match.group(2)))
    )


class ChordParser:
    tone_pattern_str = r"[A-H](?:#|b)?"
    tone_pattern = re.compile(tone_pattern_str)
    modifier_patterns: tuple[re.Pattern, Callable[..., ChordModifier], bool] = [
        (re.compile(r"maj7?"), MajorSeventh, False),
        (re.compile(r"m"), Minor, False),
        (re.compile(r"7"), DominantSeventh, False),
        (re.compile(r"\d+"), (lambda match: AddedNote(int(match.group()))), True),
        (re.compile(r"sus(\d)"), (lambda match: Suspended(int(match.group(0)))), True),
        (re.compile(r"(\+|dim)(\d)?"), _parse_altered_modifier_match, True),
        (re.compile(r"/" + tone_pattern_str), (lambda match: BassNote(match.group()[1:])), True),
    ]

    def parse(self, chord_str: str) -> Chord:
        if not chord_str:
            raise SongParseError("empty chord")
        root = self.tone_pattern.match(chord_str)
        if root is None:
            raise SongParseError(f"invalid chord major: {chord_str}")
        modifiers = list(self.parse_modifiers(chord_str[root.end() :]))
        return Chord(root.group(), modifiers=modifiers)

    def parse_modifiers(self, modif_str: str) -> Generator[ChordModifier, None, None]:
        while modif_str:
            for pattern, converter, pass_match in self.modifier_patterns:
                match = pattern.match(modif_str)
                if match is not None:
                    yield converter(match) if pass_match else converter()
                    modif_str = modif_str[len(match.group()):]
                    break
            else:
                yield GenericChordModifier(modif_str)
                return


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

    def dumps(self, song: Song, indent: int | None = None, chords: bool = True) -> str:
        header = f"\n{self.dump_heading(song)}\n\n"
        other_annots = self.dump_annotations(song, chords=chords)
        if other_annots:
            header += f"{other_annots}\n\n"
        body = "\n\n".join(self.dump_song_items(song, indent=indent, chords=chords))
        return header + body

    def dump_heading(self, song: Song) -> str:
        authors = ", ".join(annot.name for annot in song.get_annotations_of_type(AuthorAnnotation))
        try:
            title = next(annot.title for annot in song.get_annotations_of_type(TitleAnnotation))
        except StopIteration:
            title = self.untitled_title
        if authors:
            return " " * self.heading_indent + authors + self.default_heading_marker + title
        else:
            return " " * self.heading_indent + title

    def dump_annotations(self, song: Song, chords: bool = True) -> str:
        rem_annots = [
            annot for annot in song.annotations
            if not isinstance(annot, (AuthorAnnotation, TitleAnnotation))
            and (chords or not annot.is_chord_annotation)
        ]
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


class AgamaFormat(DefaultFormat):
    empty_line_pattern = re.compile(r"\n\s*\n")
    empty_startline_pattern = re.compile(r"^\s*\n")

    def dump_strophe(self, strophe: Strophe, indent: int = 0, chords: bool = True) -> str:
        init = self.dump_strophe_mark(strophe.mark, indent=indent)
        indenter = " " * indent
        dumped_segments = [self.dump_segment(seg, chords=chords) for seg in strophe.single_line_segments()]
        raw_body = self._merge_lines(dumped_segments) if chords else "".join(dumped_segments)
        if chords:
            indented_body = indenter + raw_body.replace("\n", "\n" + indenter)
            body_with_mark = self.empty_startline_pattern.sub(
                "", self.empty_line_pattern.sub("\n", indented_body.replace("\n" + indenter, "\n" + init, 1).strip("\n"))
            )
        else:
            body_with_mark = init + raw_body.replace("\n", "\n" + indenter)
        return body_with_mark

    def _merge_lines(self, dumped_segments: list[str]) -> str:
        chord_lines = [[]]
        main_lines = [[]]
        for dseg in dumped_segments:
            chord_line, main_line = dseg.split("\n", maxsplit=1)
            chord_lines[-1].append(chord_line)
            main_lines[-1].append(main_line)
            if main_line.endswith("\n"):
                chord_lines[-1][-1] = chord_lines[-1][-1].rstrip() + "\n"
                chord_lines.append([])
                main_lines.append([])
        chord_lines[-1][-1] = chord_lines[-1][-1].rstrip() + "\n"
        return "".join(
            "".join(line) for line_pair in zip(chord_lines, main_lines) for line in line_pair
        )

    def dump_segment(self, seg: StropheSegment, chords: bool = True) -> str:
        if chords:
            if isinstance(seg, ChordedSegment):
                chord_str = seg.chord.to_string()
                length = max(len(chord_str) + 1, len(seg.text))
                return chord_str.ljust(length) + "\n" + (seg.text if seg.text.endswith("\n") else seg.text.ljust(length))
            else:
                return " " * len(seg.text) + "\n" + seg.text
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
    print(AgamaFormat().dumps(song))
