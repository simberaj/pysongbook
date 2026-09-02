import abc
from abc import ABC
from collections.abc import Callable, Generator
import dataclasses
import functools
import json
import re
import warnings

from pysongbook.model import (
    AddedNote,
    Altered,
    Annotation,
    AuthorAnnotation,
    BassNote,
    BridgeMark,
    CapoAnnotation,
    Chord,
    ChordedSegment,
    ChordlessSegment,
    ChordModifier,
    ChorusMark,
    CodaMark,
    DominantSeventh,
    EmptyStropheMark,
    GenericChordModifier,
    IndeterminateChordingSegment,
    IntroMark,
    LetteredStropheMark,
    MajorSeventh,
    Minor,
    NumberedChorusMark,
    NumberedStropheMark,
    PickAnnotation,
    RecitationMark,
    RepeatedStrophePart,
    RepeatStropheWithSameMark,
    Repetition,
    SimpleStropheRepeat,
    SoloMark,
    Song,
    Strophe,
    StropheMark,
    StropheRepeat,
    StropheSegment,
    Suspended,
    TitleAnnotation,
    UnchordedSegment,
    UnknownChordSegment,
)


class SongParseError(ValueError):
    pass


class SongParseWarning(UserWarning):
    pass


class PositionalSongParseError(ValueError):
    def __init__(self, issue: str, text: str, pos: int):
        self.issue = issue
        self.pos = pos
        super().__init__(f"{issue} around {text[pos - 10 : pos + 10]!r} at {text[pos : pos + 10]!r} (index {pos})")


class SongSerializationWarning(UserWarning):
    pass


class ProcessingInstruction(Annotation):
    is_chord_annotation = False

    def to_string(self, delimiter: str) -> str:
        raise ValueError(f"cannot serialize processing instruction {self}")


class TurnChordsOn(ProcessingInstruction):
    pass


class TurnChordsOff(ProcessingInstruction):
    pass


class SongFormat(ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @property
    @abc.abstractmethod
    def can_read(self) -> bool: ...

    @property
    @abc.abstractmethod
    def can_write(self) -> bool: ...


def _parse_altered_modifier_match(match: re.Match) -> Altered:
    return Altered(direction=match.group(1), factor=(5 if not match.group(2) else int(match.group(2))))


class ChordParser(abc.ABC):
    @abc.abstractmethod
    def parse(self, chord_str: str) -> Chord:
        raise NotImplementedError


class DefaultChordParser:
    tone_pattern_str = r"[A-H](?:#|b)?"
    tone_pattern = re.compile(tone_pattern_str)
    modifier_patterns: tuple[re.Pattern, Callable[..., ChordModifier], bool] = [
        (re.compile(r"maj7?"), MajorSeventh, False),
        (re.compile(r"m"), Minor, False),
        (re.compile(r"7"), DominantSeventh, False),
        (re.compile(r"\d+"), (lambda match: AddedNote(int(match.group()))), True),
        (re.compile(r"sus(\d)"), (lambda match: Suspended(int(match.group(1)))), True),
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
                    modif_str = modif_str[len(match.group()) :]
                    break
            else:
                yield GenericChordModifier(modif_str)
                return


class ModifiedSongsLatexChordParser(ChordParser):
    substitutions: list[tuple[re.Pattern, str | Callable[[re.Match], str]]] = [
        (re.compile(r"\\shrp(\{})?"), "#"),
        (re.compile(r"\\hidx\{([^}\]]+)}"), lambda m: m.group(1)),
        (re.compile(r"\\didx\{([^}\]]+)}"), lambda m: m.group(1)),
    ]

    def __init__(self):
        self.inner = DefaultChordParser()

    def parse(self, chord_str: str) -> Chord:
        sub_chord_str = chord_str
        for pattern, sub in self.substitutions:
            sub_chord_str = pattern.sub(sub, sub_chord_str)
        parsed = self.inner.parse(sub_chord_str)
        return parsed


class DefaultFormat(SongFormat):
    name = "default"
    can_read = True
    can_write = True

    # todo initialize this with config-level options
    default_heading_marker: str = " - "
    default_strophe_mark_delimiter: str = "."
    default_annotation_delimiter: str = ": "
    chord_start_mark: str = "["
    chord_end_mark: str = "]"

    chord_parser: DefaultChordParser = DefaultChordParser()
    part_separator_pattern: re.Pattern = re.compile(r"\n\s*\n")
    whitespace_normalizers: list[tuple[re.Pattern, str]] = [
        (re.compile(r"\s*\n\s*"), "\n"),  # remove all space around newlines
        (re.compile(r"[^\S\r\n]+"), " "),  # change all space except newline to a single space
    ]
    heading_markers: list[str] = [default_heading_marker, ": "]
    strophe_mark_delimiters: list[str] = [default_strophe_mark_delimiter, ":"]
    direct_strophe_marks: dict[str, type[StropheMark]] = {
        "R": ChorusMark,
        # "C": CodaMark,  # coda recognition is done by normalization in the model
    }
    strophe_mark_patterns: list[tuple[re.Pattern, type[StropheMark]]] = [
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


class AgamaFormat(DefaultFormat):
    name = "agama"
    empty_line_pattern = re.compile(r"\n\s*\n")
    empty_startline_pattern = re.compile(r"^\s*\n")

    def loads(self, song_text: str) -> Song:
        raise NotImplementedError

    def dump_strophe(self, strophe: Strophe, indent: int = 0, chords: bool = True) -> str:
        init = self.dump_strophe_mark(strophe.mark, indent=indent)
        indenter = " " * indent
        dumped_segments = [self.dump_segment(seg, chords=chords) for seg in strophe.single_line_segments()]
        raw_body = self._merge_lines(dumped_segments) if chords else "".join(dumped_segments)
        if chords:
            indented_body = indenter + raw_body.replace("\n", "\n" + indenter)
            body_with_mark = self.empty_startline_pattern.sub(
                "",
                self.empty_line_pattern.sub("\n", indented_body.replace("\n" + indenter, "\n" + init, 1).strip("\n")),
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
        return "".join("".join(line) for line_pair in zip(chord_lines, main_lines, strict=False) for line in line_pair)

    def dump_segment(self, seg: StropheSegment, chords: bool = True) -> str:
        if chords:
            if isinstance(seg, ChordedSegment):
                chord_str = seg.chord.to_string()
                length = max(len(chord_str) + 1, len(seg.text))
                return (
                    chord_str.ljust(length) + "\n" + (seg.text if seg.text.endswith("\n") else seg.text.ljust(length))
                )
            else:
                return " " * len(seg.text) + "\n" + seg.text
        else:
            return seg.text


@dataclasses.dataclass
class EmbeddedStrophe(StropheSegment):
    strophe: Strophe

    def __add__(self, other: str):
        raise ValueError(f"cannot merge embedded strophe with {other!r}")

    def __sub__(self, other: str):
        raise ValueError(f"cannot subtract {other!r} from embedded strophe")

    @property
    def text(self) -> str:
        raise NotImplementedError

    def splitlines(self) -> list[StropheSegment]:
        raise NotImplementedError


@dataclasses.dataclass
class EmbeddedStropheMark(ProcessingInstruction):
    mark: StropheMark


@dataclasses.dataclass
class RepeatCount(ProcessingInstruction):
    n_repeats: int


@dataclasses.dataclass
class CommandArgSetting:
    min_args: int = 0
    max_args: int = 1
    raw_args: list[int] = dataclasses.field(default_factory=list)


class ModifiedSongsLatexFormat(SongFormat):
    name = "latex-songs-modif"
    can_read = True
    can_write = True

    beginsong_pattern = re.compile(r"\s*\\beginsong\{(?P<title>[^}]+?)}(?:\[(?P<annots>[^]]+?)])?")
    beginsong_annot_pattern = re.compile(r"(?P<key>[a-z]+)=\{(?P<value>[^}]*?)}")
    beginsong_annot_keys = {"by": AuthorAnnotation}
    simple_beginverse_commands: dict[str, type[StropheMark]] = {
        "emptyv": EmptyStropheMark,
        "freev": EmptyStropheMark,
        "chor": ChorusMark,
        "intro": IntroMark,
        "solo": SoloMark,
        "bridge": BridgeMark,
        "chorusi": functools.partial(NumberedChorusMark, number=1),
        "chorusii": functools.partial(NumberedChorusMark, number=2),
        "averse": functools.partial(LetteredStropheMark, letter="A"),
        "bverse": functools.partial(LetteredStropheMark, letter="B"),
        "cverse": functools.partial(LetteredStropheMark, letter="C"),
        "recite": RecitationMark,
    }
    simple_beginverse_command_names = {v(): k for k, v in simple_beginverse_commands.items()}
    simple_beginverse_command_names[CodaMark()] = "cverse"
    numbered_beginverse_command = "num"
    beginverse_commands = [numbered_beginverse_command] + list(simple_beginverse_commands.keys())
    endverse_commands = ["fin", "cl"]
    strophe_split_pattern = re.compile(r"\\(?=(?:" + "|".join(beginverse_commands) + r")\b)")
    endverse_pattern = re.compile(r"\\(?:" + "|".join(endverse_commands) + r")\b")
    strophe_token_pattern = re.compile(r"([]\\[{}])")
    command_name_pattern = re.compile(r"\w+")
    whitespace_pattern = re.compile(r"\s+")
    noop_commands = ["emptyspace", r"\\", "qquad"]
    chord_parser = ModifiedSongsLatexChordParser()
    chord_level_commands = {
        0: "{}",
        1: "\\hidx{{{}}}",
        -1: "\\didx{{{}}}",
    }
    strophe_mark_commands: dict[StropheMark, str] = {
        EmptyStropheMark(): "nempty",
        ChorusMark(): "nchorus",
        NumberedChorusMark(number=1): "nchorusi",
        NumberedChorusMark(number=2): "nchorusii",
        LetteredStropheMark(letter="A"): "naverse",
        LetteredStropheMark(letter="B"): "nbverse",
        LetteredStropheMark(letter="C"): "ncverse",
        IntroMark(): "nintro",
        SoloMark(): "nsolo",
        BridgeMark(): "nbridge",
        RecitationMark(): "nrecite",
    }
    simple_text_commands: dict[str, list[StropheSegment | ProcessingInstruction]] = {
        "chordson": [TurnChordsOn()],
        "chordsoff": [TurnChordsOff()],
        "ldots": [IndeterminateChordingSegment("...")],
        "endsong": [],
    }
    for mark, command in strophe_mark_commands.items():
        simple_text_commands[command] = [EmbeddedStropheMark(mark)]
    text_load_repls: dict[str, str] = {
        "~-- ": " - ",
        " -- ": " - ",
    }
    text_load_patterns: dict[re.Pattern, str] = {re.compile(r"\s+\n"): "\n"}
    text_dump_repls: dict[str, str] = {v: k for k, v in text_load_repls.items()} | {
        "\n": "\\\\\n",
        "...": "\\ldots{}",
        " - ": "~-- ",
    }
    text_dump_patterns: dict[re.Pattern, str] = {re.compile(r"\((?P<inner>[^\\)]+)\)"): r"\\emph{(\1)}"}
    repcommands = {
        ChorusMark(): "repchorus",
        NumberedChorusMark(number=1): "repchorusi",
        NumberedChorusMark(number=2): "repchorusii",
    }
    no_chord_brace_length_multiple = 1.75
    no_chord_brace_length = 3
    command_arg_settings: dict[str, CommandArgSetting] = {
        "capo": CommandArgSetting(min_args=1, max_args=1, raw_args=[0]),
        "pick": CommandArgSetting(min_args=1, max_args=1, raw_args=[0]),
        "repsec": CommandArgSetting(min_args=2, max_args=2, raw_args=[]),
    }

    def loads(self, song_text: str) -> Song:
        annotations, remnant = self._parse_beginsong(song_text)
        strophe_strs = self.strophe_split_pattern.split(remnant)
        if len(strophe_strs) < 3:
            raise SongParseError("no strophes found")
        annotations.extend(self._parse_annotations(strophe_strs[0].strip()))
        items: list[Annotation | Strophe] = []
        num = 1
        chords_on = True
        for verse_str in strophe_strs[1:]:
            strophe, poststrophe_content = self._parse_strophe(verse_str.strip(), num=num, chords_on=chords_on)
            chords_on_update, poststrophe_content = process_chords_on_instructions(poststrophe_content)
            if chords_on_update is not None:
                chords_on = chords_on_update
            if strophe:
                if isinstance(strophe.mark, NumberedStropheMark):
                    num += 1
                items.append(strophe)
            if poststrophe_content:
                for item in poststrophe_content:
                    if isinstance(item, EmbeddedStrophe):
                        items.append(item.strophe)
                    elif isinstance(item, Annotation):
                        items.append(item)
                    else:
                        raise ValueError(f"unknown post-strophe content: {item!r}")
        return Song(annotations=annotations, items=items)

    def _parse_beginsong(self, song_text: str) -> tuple[list[Annotation], str]:
        match = self.beginsong_pattern.match(song_text)
        if not match:
            raise SongParseError("\\beginsong not found at beginning of song")
        annotations = [TitleAnnotation(match.group("title"))]
        other_annot_str = match.group("annots")
        while other_annot_str:
            annot_match = self.beginsong_annot_pattern.match(other_annot_str)
            if not annot_match:
                break
            key = annot_match.group("key")
            value = annot_match.group("value")
            if key in self.beginsong_annot_keys:
                annotations.append(self.beginsong_annot_keys[key](value))
            else:
                warnings.warn(f"unknown \\beginsong annotation key: {key}={value}")
            other_annot_str = other_annot_str[annot_match.end() :]
        if other_annot_str:
            warnings.warn(f"unprocessed \\beginsong content: {other_annot_str!r}", category=SongParseWarning)
        return annotations, song_text[match.end() :].lstrip()

    def _parse_annotations(self, annot_str: str) -> list[Annotation]:
        raw = self._parse_annotation_chunk(annot_str)
        for result in raw:
            if not isinstance(result, Annotation):
                raise ValueError(f"non-annotation encountered in annotation block: {result!r}")
        return raw

    def _parse_annotation_chunk(self, annot_str: str) -> list[EmbeddedStrophe | Annotation]:
        # ANNOT_CHUNK = (COMMAND_CHUNK | "\s"+)*
        strophes_and_annots = []
        current_pos = 0
        while current_pos < len(annot_str):
            current_pos = self._skip_whitespace(annot_str, pos=current_pos)
            part_results, current_pos = self._parse_command_chunk(annot_str, pos=current_pos)
            for result in part_results:
                if isinstance(result, EmbeddedStrophe | Annotation):
                    if isinstance(result, EmbeddedStrophe):
                        result = EmbeddedStrophe(
                            type(result.strophe)(
                                mark=result.strophe.mark,
                                # chords_on=True here to allow chorded segment merging
                                segments=self._join_strophe_segments(result.strophe.segments, chords_on=True),
                            )
                        )
                    strophes_and_annots.append(result)
                else:
                    raise ValueError(f"invalid annotation chunk content: {result!r} from {annot_str!r}")
        return strophes_and_annots

    def _skip_whitespace(self, text: str, pos: int) -> int:
        whitespace_match = self.whitespace_pattern.match(text[pos:])
        if whitespace_match:
            return pos + len(whitespace_match.group())
        else:
            return pos

    def _parse_strophe(self, strophe_str: str, num: int, chords_on: bool) -> tuple[Strophe, list[Annotation]]:
        mark_str = re.match(r"\w+", strophe_str).group()
        mark = self._parse_strophe_mark(mark_str, num=num)
        parts = self.endverse_pattern.split(strophe_str[len(mark_str) :])
        if len(parts) != 2:
            raise SongParseError("mismatched strophe start/end commands")
        body, afterpart = [part.strip() for part in parts]
        strophe = Strophe(mark=mark, segments=self._parse_strophe_segments(body, chords_on=chords_on))
        return strophe, self._parse_annotation_chunk(afterpart)

    def _parse_strophe_mark(self, mark_str: str, num: int) -> StropheMark:
        if mark_str == self.numbered_beginverse_command:
            return NumberedStropheMark(num)
        elif mark_str in self.simple_beginverse_commands:
            return self.simple_beginverse_commands[mark_str]()
        else:
            raise SongParseError(f"unknown strophe mark command: {mark_str!r}")

    def _parse_strophe_segments(self, body: str, chords_on: bool) -> list[StropheSegment]:
        # STROPHE = STROPHE_PART+
        # STROPHE_PART = COMMAND_CHUNK | STROPHE_CHUNK
        # COMMAND_CHUNK = "\" COMMAND_NAME CURLY_PARS?
        # COMMAND_NAME = "\w"+ | "\"
        # STROPHE_CHUNK = CHORD_CHUNK? TEXT_CHUNK
        # CURLY_PARS = "{" STROPHE_PART* "}"
        # CHORD_CHUNK = CHORD_MARK CURLY_PARS?
        # TEXT_CHUNK = "[^[]{}\]"
        # CHORD_MARK = "\[" "[^]]" "]"
        strophe_segments = []
        current_pos = 0
        while current_pos < len(body):
            part_segments, current_pos = self._parse_strophe_part(body, pos=current_pos)
            strophe_segments.extend(part_segments)
        return self._join_strophe_segments(strophe_segments, chords_on=chords_on)

    @classmethod
    def _join_strophe_segments(cls, segments: list[StropheSegment], chords_on: bool) -> list[StropheSegment]:
        seg_i = 0
        current_chords_on = chords_on
        while seg_i < len(segments):
            if isinstance(segments[seg_i], TurnChordsOn):
                current_chords_on = True
                segments.pop(seg_i)
            elif isinstance(segments[seg_i], TurnChordsOff):
                current_chords_on = False
                segments.pop(seg_i)
            elif isinstance(segments[seg_i], Repetition):
                segments[seg_i] = Repetition(
                    segments=cls._join_strophe_segments(segments[seg_i].segments, current_chords_on),
                    n_repeats=segments[seg_i].n_repeats
                )
                seg_i += 1
            elif isinstance(segments[seg_i], IndeterminateChordingSegment):
                if seg_i > 0 and (
                    (current_chords_on and isinstance(segments[seg_i - 1], ChordedSegment | UnknownChordSegment))
                    or (not current_chords_on and isinstance(segments[seg_i - 1], UnchordedSegment))
                ):
                    # merge the segment to the preceding one based on the preceding one's type:
                    # chorded/unknownchord: merge if chords on
                    # unchorded: merge if chords off
                    joined_text = segments[seg_i - 1].text + segments[seg_i].text
                    if isinstance(segments[seg_i - 1], ChordedSegment):
                        segments[seg_i - 1] = ChordedSegment(chord=segments[seg_i - 1].chord, text=joined_text)
                    else:
                        segments[seg_i - 1] = segments[seg_i - 1].__class__(text=joined_text)
                    segments.pop(seg_i)
                else:
                    # an indeterminate segment at the start of a strophe (or barred from merging with the previous
                    # segment, e.g. by change of chords_on): if chords are on, it should have a chord but does
                    # not, so marking as unknown chord segment; otherwise it is meant to be unchorded
                    ctype = UnknownChordSegment if current_chords_on else UnchordedSegment
                    segments[seg_i] = ctype(text=segments[seg_i].text)
                    seg_i += 1
            elif isinstance(segments[seg_i], RepeatCount) and seg_i > 0:
                for j in range(1, seg_i + 1):
                    if isinstance(segments[seg_i - j], Repetition):
                        segments[seg_i - j].n_repeats = segments[seg_i].n_repeats
                        for k in range(j):
                            # Remove all intervening empty space segments.
                            segments.pop(seg_i - k)
                        break
                    elif not isinstance(segments[seg_i - j], ChordlessSegment) or segments[seg_i - j].text.strip():
                        # Skip through empty space segments when finding a corresponding repetition segment.
                        break
            else:
                seg_i += 1
        return segments

    def _parse_strophe_part(self, text: str, pos: int) -> tuple[list[StropheSegment | ProcessingInstruction], int]:
        if text[pos] == "\\" and text[pos:pos+2] != "\\[":
            return self._parse_command_chunk(text, pos)
        return self._parse_strophe_chunk(text, pos)

    def _parse_command_chunk(self, text: str, pos: int) -> tuple[list[StropheSegment | ProcessingInstruction], int]:
        if text[pos] != "\\" or len(text) <= pos + 1:
            raise PositionalSongParseError("expecting \\ followed by a command name", text, pos)
        pos += 1
        if text[pos] == "\\":
            return [], pos + 1  # newline command is no-op
        command_name_match = self.command_name_pattern.match(text[pos:])
        if not command_name_match:
            raise PositionalSongParseError("expecting command name", text, pos)
        command_name = command_name_match.group()
        post_command_name_pos = pos + len(command_name)
        args, after_pos = self._parse_command_args(
            text, post_command_name_pos, setting=self.command_arg_settings.get(command_name, CommandArgSetting())
        )
        if not args:
            # skip whitespace after command name if no braces present
            after_pos = post_command_name_pos + (
                len(text[post_command_name_pos:]) - len(text[post_command_name_pos:].lstrip())
            )
        if command_name in self.simple_text_commands:
            if args and args[0]:
                raise PositionalSongParseError("nonempty contents of simple command", text, pos)
            return self.simple_text_commands[command_name], after_pos
        elif command_name in self.noop_commands:
            return (args[0] if args else []), after_pos
        else:
            return self.complex_text_commands[command_name](*args), after_pos

    def _parse_command_args(
        self, text: str, pos: int, setting: CommandArgSetting
    ) -> tuple[list[list[StropheSegment]], int]:
        args = []
        after_pos = pos
        for i in range(setting.max_args):
            if after_pos < len(text) and text[after_pos] == "{":
                if i in setting.raw_args:
                    arg, after_pos = self._parse_raw_curly_parens(text, after_pos)
                else:
                    arg, after_pos = self._parse_curly_parens(text, after_pos)
                args.append(arg)
        return args, after_pos

    def _parse_strophe_chunk(self, text: str, pos: int) -> tuple[list[StropheSegment], int]:
        segments = []
        try:
            chord_segment, after_chord_pos = self._parse_chord_chunk(text, pos)
            segments.append(chord_segment)
        except PositionalSongParseError:
            after_chord_pos = pos
        if after_chord_pos < len(text):
            plain_segment, after_plain_pos = self._parse_text_chunk(text, after_chord_pos)
            if plain_segment is not None:
                segments.append(plain_segment)
        else:
            after_plain_pos = after_chord_pos
        return segments, after_plain_pos

    def _parse_text_chunk(self, text: str, pos: int) -> tuple[IndeterminateChordingSegment | None, int]:
        split_result = self.strophe_token_pattern.split(text[pos:], maxsplit=1)
        if len(split_result) == 1:  # no more token splitters, all the rest is plain
            return self._handle_parsed_text(text[pos:]), len(text)
        pretoken, token, posttoken = split_result
        if pretoken:
            return self._handle_parsed_text(pretoken), pos + len(pretoken)
        return None, pos

    def _handle_parsed_text(self, parsed: str) -> IndeterminateChordingSegment:
        for pat, sub in self.text_load_repls.items():
            parsed = parsed.replace(pat, sub)
        for pat, sub in self.text_load_patterns.items():
            parsed = pat.sub(sub, parsed)
        return IndeterminateChordingSegment(parsed)

    def _parse_chord_chunk(self, text: str, pos: int) -> tuple[StropheSegment, int]:
        chord, after_chord_pos = self._parse_chord_mark(text, pos)
        if after_chord_pos < len(text) and text[after_chord_pos].startswith("{"):
            inner_chunk, after_brace_pos = self._parse_curly_parens(text, after_chord_pos)
            # this inner chunk should be a simple plain segment
            if len(inner_chunk) != 1 or not isinstance(inner_chunk[0], ChordlessSegment):
                raise PositionalSongParseError("non-plain chord scope parentheses content", text, after_chord_pos)
            inner_text = inner_chunk[0].text
        else:
            inner_text = ""
            after_brace_pos = after_chord_pos
        return ChordedSegment(chord=chord, text=inner_text), after_brace_pos

    def _parse_curly_parens(self, text: str, pos: int) -> tuple[list[StropheSegment], int]:
        if text[pos] != "{":
            raise PositionalSongParseError("expecting {", text, pos)
        current_pos = pos + 1
        inner_segments = []
        while text[current_pos] != "}":
            inner_chunk_segments, current_pos = self._parse_strophe_part(text, current_pos)
            inner_segments.extend(inner_chunk_segments)
        return inner_segments, current_pos + 1

    @staticmethod
    def _parse_raw_curly_parens(text: str, pos: int) -> tuple[str, int]:
        if text[pos] != "{":
            raise PositionalSongParseError("expecting {", text, pos)
        current_pos = pos + 1
        end_pos = text.find("}", current_pos)
        return text[current_pos:end_pos], end_pos + 1

    def _parse_chord_mark(self, text: str, pos: int) -> tuple[Chord, int]:
        if not text[pos:].startswith("\\["):
            raise PositionalSongParseError("expecting chord start (\\[)", text, pos)
        pos += 2
        next_ending = text[pos:].find("]")
        if next_ending == -1:
            raise PositionalSongParseError("unterminated chord", text, pos)
        chord = self.chord_parser.parse(text[pos : pos + next_ending])
        return chord, pos + next_ending + 1

    @staticmethod
    def _parse_repsec_marker(markers: list[StropheSegment | ProcessingInstruction]) -> StropheMark:
        if len(markers) != 1:
            raise ValueError(f"invalid repsec marker: {markers!r}")
        marker = markers[0]
        if isinstance(marker, EmbeddedStropheMark):
            return marker.mark
        elif isinstance(marker, ChordlessSegment) and marker.text.strip().isdigit():
            return NumberedStropheMark(int(marker.text.strip()))
        else:
            raise ValueError(f"invalid repsec marker: {marker!r}")

    @staticmethod
    def _parse_repsec_marked(segs: list[StropheSegment | ProcessingInstruction], mark: StropheMark) -> list[EmbeddedStrophe]:
        if segs and isinstance(segs[-1], RepeatCount):
            n_repeats = segs[-1].n_repeats
            segs.pop()
        else:
            n_repeats = 1
        emb_strophe = EmbeddedStrophe(RepeatStropheWithSameMark(mark=mark, segments=segs))
        return [emb_strophe] * n_repeats

    complex_text_commands: dict[
        str, Callable[[list[StropheSegment | ProcessingInstruction]], list[StropheSegment | ProcessingInstruction]]
    ] = {
        "cseq": (lambda segs: segs),
        "uv": (lambda segs: [IndeterminateChordingSegment('"')] + segs + [IndeterminateChordingSegment('"')]),
        "emph": (lambda segs: segs),
        "rep": (lambda segs: [RepeatCount(int(segs[0].text))]),
        "repchorus": functools.partial(_parse_repsec_marked, mark=ChorusMark()),
        "repchorusi": functools.partial(_parse_repsec_marked, mark=NumberedChorusMark(number=1)),
        "repchorusii": functools.partial(_parse_repsec_marked, mark=NumberedChorusMark(number=2)),
        "capo": (lambda arg: [CapoAnnotation(int(arg))]),
        "pick": (lambda arg: [PickAnnotation(arg)]),
        "reppart": (lambda segs: [Repetition(segs)]),
        "repsec": (lambda markers, segs, rm=_parse_repsec_marked, rr=_parse_repsec_marker: rm(segs, rr(markers))),
    }

    def dumps(self, song: Song, chords: bool = True) -> str:
        parts = [self.dump_beginsong(song)]
        annot_part = self.dump_annotations(song, chords=chords)
        if annot_part:
            parts.append(annot_part)
        parts.extend(self.dump_song_items(song, chords=chords))
        parts.append(self.dump_endsong(song))
        return "\n".join(parts)

    def dump_beginsong(self, song: Song) -> str:
        authors = [auth_annot.name for auth_annot in song.get_annotations_of_type(AuthorAnnotation)]
        meta = f"[by={{{', '.join(authors)}}}]" if authors else ""  # TODO more annotation types to cover songs meta tag
        return f"\\beginsong{{{song.get_title()}}}{meta}\n\\chordsoff"

    def dump_endsong(self, song: Song) -> str:
        return "\\endsong"

    def dump_annotations(self, song: Song, chords: bool = True) -> str:
        rem_annots = song.get_displayable_annotations(chords=chords)
        if not rem_annots:
            return ""
        return "\n".join(self.dump_annotation(annot) for annot in rem_annots)

    def dump_annotation(self, annot: Annotation) -> str:
        if isinstance(annot, CapoAnnotation):
            return f"\\capo{{{annot.fret}}}"
        elif isinstance(annot, PickAnnotation):
            return f"\\pick{{{annot.pattern}}}"
        raise TypeError(f"unknown annotation type: {annot!r}")

    def dump_song_items(self, song: Song, chords: bool) -> Generator[str, None, None]:
        accummulated_repeats = []
        for i, item in enumerate(song.items):
            if isinstance(item, Annotation) and (chords or not item.is_chord_annotation):
                yield self.dump_annotation(item)
            elif isinstance(item, SimpleStropheRepeat):
                accummulated_repeats.append(item)
                # TODO handle modified strophe repeats
                if (
                    i + 1 == len(song.items)
                    or not isinstance(song.items[i + 1], SimpleStropheRepeat)
                    or song.items[i + 1].repeated_strophe != item.repeated_strophe
                ):
                    yield self.dump_simple_strophe_repeat(
                        accummulated_repeats[0], chords=chords, n=len(accummulated_repeats)
                    )
                    accummulated_repeats = []
            elif isinstance(item, StropheRepeat):
                yield self.dump_strophe_repeat(item, chords=chords)
            else:
                yield self.dump_strophe(item, chords=chords)

    def dump_strophe(self, strophe: Strophe, chords: bool) -> str:
        if isinstance(strophe, RepeatStropheWithSameMark):
            raise ValueError("cannot dump unlinked strophe repeat")
        elif isinstance(strophe, SimpleStropheRepeat):
            raise ValueError("cannot dump simple strophe repeat: should be dumped via separate pathway")
        content = self.dump_segments(strophe.segments, chords=chords)
        beginverse = self.dump_beginverse(strophe.mark)
        endverse = "\\fin" if isinstance(strophe.mark, NumberedStropheMark) else "\\cl"
        if content:
            return "\n".join((beginverse, content, endverse))
        else:
            return beginverse + "\\emptyspace\\\\" + endverse

    def dump_simple_strophe_repeat(self, strophe: SimpleStropheRepeat, chords: bool, n: int = 1) -> str:
        _ = chords
        inner = f"\\rep{{{n}}}" if n > 1 else "\\emptyspace"
        return self.dump_any_strophe_repeat(strophe.mark, inner)

    def dump_strophe_repeat(self, strophe: StropheRepeat, chords: bool) -> str:
        inner = self.dump_segments(
            [seg for seg in strophe.segments if not isinstance(seg, RepeatedStrophePart)], chords=chords
        )
        return self.dump_any_strophe_repeat(strophe.mark, inner)

    def dump_any_strophe_repeat(self, mark: StropheMark, inner: str):
        if mark in self.repcommands:
            repcommand = self.repcommands[mark]
            return f"\\{repcommand}{{{inner}}}"
        elif mark in self.strophe_mark_commands:
            return f"\\repsec{{\\{self.strophe_mark_commands[mark]}}}{{{inner}}}"
        elif isinstance(mark, NumberedStropheMark):
            return f"\\repsec{{{mark.number}}}{{{inner}}}"
        else:
            raise TypeError(f"unknown strophe repeat mark: {mark!r}")

    def dump_beginverse(self, mark: StropheMark) -> str:
        if isinstance(mark, NumberedStropheMark):
            return "\\num"
        elif mark in self.simple_beginverse_command_names:
            return f"\\{self.simple_beginverse_command_names[mark]}"
        else:
            raise ValueError(f"cannot serialize {mark}")

    def dump_segments(self, segments: list[StropheSegment], chords: bool) -> str:
        dumped = []
        if chords and segments and isinstance(segments[0], ChordedSegment):
            if all(isinstance(seg, ChordedSegment) and (not seg.text or seg.text.isspace()) for seg in segments):
                return self.dump_cseq(segments)
            dumped.append("\\chordson\n")
        prev_seg = None
        for seg in segments:
            dumped.extend(self.dump_segment(seg, chords=chords, prev_seg=prev_seg))
            prev_seg = seg
        return "".join(dumped).replace("\n\n", "\n")

    def dump_segment(self, seg: StropheSegment, chords: bool, prev_seg: StropheSegment | None):
        if isinstance(seg, ChordedSegment) and chords:
            if isinstance(prev_seg, UnchordedSegment):
                yield "\n\\chordson\n"
            dumped_chord = self.dump_chord(seg.chord)
            yield f"\\[{dumped_chord}]"
            if seg.text and not seg.text.isspace():
                if "\n" in seg.text:
                    first_line, other_lines = seg.text.split("\n", maxsplit=1)
                    if first_line:
                        yield self._dump_chorded_text(first_line, len(dumped_chord), endline=True)
                        yield "\\\\\n"
                    yield self.dump_text(other_lines)
                else:
                    yield self._dump_chorded_text(seg.text, len(dumped_chord))
        elif (
            isinstance(seg, UnchordedSegment)
            or isinstance(seg, UnknownChordSegment)
            or (isinstance(seg, ChordedSegment) and not chords)
        ):
            if chords and isinstance(prev_seg, ChordedSegment):
                yield "\n\\chordsoff\n"
            if isinstance(seg, UnknownChordSegment) and prev_seg is not None:
                pass  # TODO warn that we have unknown chording elsewhere than start of strophe
            yield self.dump_text(seg.text)
        elif isinstance(seg, RepeatCount):
            yield f"\\rep{{{seg.n_repeats}}}"
        elif isinstance(seg, Repetition):
            inner = self.dump_segments(seg.segments, chords=chords)
            yield f"\\reppart{{{inner}}}"
            if seg.n_repeats > 2:
                yield f" \\rep{{{seg.n_repeats}}}"
        else:
            raise ValueError(f"unknown segment type: {seg}")

    def dump_cseq(self, segments: list[ChordedSegment]) -> str:
        fake_prev_seg = ChordedSegment(chord=Chord(root="C", modifiers=[]), text="")
        return (
            "\\chordson\\cseq{"
            + "".join(
                chunk for seg in segments for chunk in self.dump_segment(seg, chords=True, prev_seg=fake_prev_seg)
            )
            + "}\\\\"
        )

    def _dump_chorded_text(self, text: str, chord_length: int, endline: bool = False) -> str:
        dumped_text = self.dump_text(text)
        no_brace_length = max(chord_length * self.no_chord_brace_length_multiple, self.no_chord_brace_length)
        if len(text.split()[0]) >= no_brace_length:
            return dumped_text
        noendspaced_text = dumped_text.rstrip()
        tail = "" if noendspaced_text == dumped_text else dumped_text[-(len(dumped_text) - len(noendspaced_text)) :]
        extender = "\\qquad" if endline and len(text) < no_brace_length else ""
        return "{" + noendspaced_text + extender + "}" + tail

    def dump_chord(self, chord: Chord) -> str:
        modif_groups = []
        for i, modif in enumerate(chord.modifiers):
            if modif_groups and modif.level == modif_groups[-1][0]:
                modif_groups[-1][1].append(modif.to_string())
            else:
                modif_groups.append((modif.level, [modif.to_string()]))
        dumped = [chord.root.replace("#", "\\shrp{}")]
        for level, group in modif_groups:
            dumped_group = "".join(group)
            dumped.append(self.chord_level_commands[level].format(dumped_group))
        return "".join(dumped)

    def dump_text(self, some_text: str) -> str:
        if '"' in some_text:
            some_text = self.dump_quoted_text(some_text)
        for pat, sub in self.text_dump_repls.items():
            some_text = some_text.replace(pat, sub)
        for pat, sub in self.text_dump_patterns.items():
            some_text = pat.sub(sub, some_text)
        return some_text

    def dump_quoted_text(self, some_text: str) -> str:
        parts = some_text.split('"')
        quoted_text = ""
        for i, part in enumerate(parts):
            if i % 2 == 0:
                quoted_text += part
            else:
                quoted_text += f"\\uv{{{part}}}"
        return quoted_text


class ModelDictFormat(SongFormat):
    name = "dict"
    can_read = False
    can_write = True

    def dumps(self, song: Song) -> str:
        return json.dumps(dataclasses.asdict(song))


def process_chords_on_instructions(annots: list[Annotation]) -> tuple[bool | None, list[Annotation]]:
    chords_on: bool | None = None
    annots_left = []
    for annot in annots:
        if isinstance(annot, TurnChordsOn):
            chords_on = True
        elif isinstance(annot, TurnChordsOff):
            chords_on = False
        else:
            annots_left.append(annot)
    return chords_on, annots_left


if __name__ == "__main__":
    from pathlib import Path
    import pprint

    chords_path = Path(__file__).parent.parent / "test" / "data"
    format = ModifiedSongsLatexFormat()
    for path in chords_path.iterdir():
        if path.suffix == ".tex" and "amelie" in str(path):
            text = path.open(encoding="utf8").read()
            print(text)
            song = format.loads(text).normalized()
            pprint.pprint(song)
            result = format.dumps(song, chords=True)
            print(result)

    # # ahoj_slunko_path = Path(__file__).parent.parent / "test" / "data" / "ahoj_slunko.txt"
    # # with ahoj_slunko_path.open(encoding="utf8") as f:
    # #     song = DefaultFormat().loads(f.read())
    # # pprint.pprint(song)
    # # print(DefaultFormat().dumps(song))
    # # print(AgamaFormat().dumps(song))
    # # ahoj_slunko_path = Path(__file__).parent.parent / "test" / "data" / "1plus1.tex"
    # ahoj_slunko_path = Path(__file__).parent.parent / "test" / "data" / "ahoj_slunko.tex"
    # with ahoj_slunko_path.open(encoding="utf8") as f:
    #     test_song = ModifiedSongsLatexFormat().loads(f.read())
    # pprint.pprint(test_song)
    # normalized_song = test_song.normalized()
    # pprint.pprint(normalized_song)
    # print(ModifiedSongsLatexFormat().dumps(normalized_song))
    # # print(DefaultFormat().dumps(test_song))
    # # print(AgamaFormat().dumps(song))

# TODO remaining songs-latex-modif features (music notes, tablatures)
