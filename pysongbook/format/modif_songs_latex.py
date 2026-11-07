import abc
from collections.abc import Callable, Generator
import dataclasses
import functools
import logging
import re
from typing import ClassVar, cast

from pysongbook.format.chord import ChordParser, TextChordParser
from pysongbook.format.core import (
    CommandArgSetting,
    EmbeddedAnnotation,
    EmbeddedStrophe,
    EmbeddedStropheMark,
    PositionalSongParseError,
    ProcessingInstruction,
    RepeatCount,
    SongFormat,
    SongParseError,
    TurnChordsOff,
    TurnChordsOn,
    process_chords_on_instructions,
)
from pysongbook.model import (
    Annotation,
    AuthorAnnotation,
    BridgeMark,
    CapoAnnotation,
    Chord,
    ChordedSegment,
    ChordlessSegment,
    ChorusMark,
    CodaMark,
    EmptyStropheMark,
    FadeOutAnnotation,
    IndeterminateChordingSegment,
    IntroMark,
    LetteredStropheMark,
    NoteAnnotation,
    NumberedChorusMark,
    NumberedStropheMark,
    PickAnnotation,
    RecitationMark,
    RepeatStropheWithSameMark,
    Repetition,
    ShowChordTab,
    SimpleStropheRepeat,
    SoloMark,
    Song,
    StringPositions,
    Strophe,
    StropheMark,
    StropheRepeat,
    StropheSegment,
    TitleAnnotation,
    TransposeAnnotation,
    UnchordedSegment,
    UnknownChordSegment,
)
from pysongbook.modify import NORMALIZER


@dataclasses.dataclass
class ModifiedSongsLatexChordParser(ChordParser):
    inner: ChordParser = dataclasses.field(default_factory=TextChordParser)
    substitutions: list[tuple[re.Pattern, str | Callable[[re.Match], str]]] = dataclasses.field(
        default_factory=lambda: [
            (re.compile(r"\\shrp(\{})?"), "#"),
            (re.compile(r"\\hidx\{([^}\]]+)}"), lambda m: m.group(1)),
            (re.compile(r"\\didx\{([^}\]]+)}"), lambda m: m.group(1)),
        ]
    )

    def parse(self, chord_str: str) -> Chord:
        sub_chord_str = chord_str
        for pattern, sub in self.substitutions:
            sub_chord_str = pattern.sub(sub, sub_chord_str)
        parsed = self.inner.parse(sub_chord_str)
        return parsed


class LaTeXSegmentCommandParser(abc.ABC):
    command_name: str
    arg_setting: ClassVar[CommandArgSetting] = CommandArgSetting()

    @abc.abstractmethod
    def parse(self, segs: list[StropheSegment | ProcessingInstruction]) -> list[StropheSegment | ProcessingInstruction]:
        raise NotImplementedError


@dataclasses.dataclass
class SimpleCommandParser(LaTeXSegmentCommandParser):
    command_name: str
    result: list[StropheSegment | ProcessingInstruction]

    def parse(self, segs: list[StropheSegment | ProcessingInstruction]) -> list[StropheSegment | ProcessingInstruction]:
        if segs:
            logging.warning(f"Skipping inner content for empty-content command {self.command_name}: {segs!r}")
        return self.result


@dataclasses.dataclass
class PassthroughSegmentCommandParser(LaTeXSegmentCommandParser):
    command_name: str

    def parse(self, segs: list[StropheSegment | ProcessingInstruction]) -> list[StropheSegment | ProcessingInstruction]:
        return segs


class QuotesCommandParser(LaTeXSegmentCommandParser):
    command_name = "uv"

    def parse(self, segs: list[StropheSegment | ProcessingInstruction]) -> list[StropheSegment | ProcessingInstruction]:
        return [IndeterminateChordingSegment('"'), *segs, IndeterminateChordingSegment('"')]


class RepetitionCommandParser(LaTeXSegmentCommandParser):
    command_name = "reppart"

    def parse(self, segs: list[StropheSegment | ProcessingInstruction]) -> list[StropheSegment | ProcessingInstruction]:
        return [Repetition(cast(list[StropheSegment], segs))]


class RepeatCountCommandParser(LaTeXSegmentCommandParser):
    command_name = "rep"

    def parse(self, segs: list[StropheSegment | ProcessingInstruction]) -> list[StropheSegment | ProcessingInstruction]:
        return [RepeatCount(int(segs[0].text))]


class BaseStropheRepetitionCommandParser(LaTeXSegmentCommandParser, abc.ABC):
    @staticmethod
    def _parse(
        segs: list[StropheSegment | ProcessingInstruction], mark: StropheMark
    ) -> list[StropheSegment | ProcessingInstruction]:
        if segs and isinstance(segs[-1], RepeatCount):
            n_repeats = segs[-1].n_repeats
            segs.pop()
        else:
            n_repeats = 1
        emb_strophe = EmbeddedStrophe(RepeatStropheWithSameMark(mark=mark, segments=cast(list[StropheSegment], segs)))
        return [emb_strophe] * n_repeats


@dataclasses.dataclass
class FixedStropheMarkRepetitionCommandParser(BaseStropheRepetitionCommandParser):
    command_name: str
    mark: StropheMark

    def parse(self, segs: list[StropheSegment | ProcessingInstruction]) -> list[StropheSegment | ProcessingInstruction]:
        return self._parse(segs, self.mark)


class StropheRepetitionCommandParser(BaseStropheRepetitionCommandParser):
    command_name: str = "repsec"
    arg_setting: ClassVar[CommandArgSetting] = CommandArgSetting(min_args=2, max_args=2, raw_args=())

    def parse(
        self,
        segs: list[StropheSegment | ProcessingInstruction],
        mark_segs: list[StropheSegment | ProcessingInstruction],
    ) -> list[StropheSegment | ProcessingInstruction]:
        mark = self._parse_strophe_mark(mark_segs)
        return self._parse(segs, mark)

    @staticmethod
    def _parse_strophe_mark(mark_segs: list[StropheSegment | ProcessingInstruction]) -> StropheMark:
        if len(mark_segs) != 1:
            raise ValueError(f"invalid repsec marker: {mark_segs!r}")
        marker = mark_segs[0]
        if isinstance(marker, EmbeddedStropheMark):
            return marker.mark
        elif isinstance(marker, ChordlessSegment) and marker.text.strip().isdigit():
            return NumberedStropheMark(int(marker.text.strip()))
        else:
            raise ValueError(f"invalid repsec marker: {marker!r}")


@dataclasses.dataclass
class FixedEmbeddedAnnotationCommandParser(LaTeXSegmentCommandParser):
    command_name: str
    annotation: Annotation
    arg_setting: ClassVar[CommandArgSetting] = CommandArgSetting(min_args=0, max_args=0, raw_args=())

    def parse(self) -> list[StropheSegment | ProcessingInstruction]:
        return [EmbeddedAnnotation(self.annotation)]


@dataclasses.dataclass
class LaTeXAnnotationCommandParser(abc.ABC):
    command_name: str
    arg_setting: ClassVar[CommandArgSetting] = CommandArgSetting(min_args=1, max_args=1, raw_args=(0,))

    @abc.abstractmethod
    def parse(self, arg: str) -> list[Annotation]:
        raise NotImplementedError


class CapoAnnotationParser(LaTeXAnnotationCommandParser):
    command_name = "capo"

    def parse(self, arg: str) -> list[CapoAnnotation]:
        return [CapoAnnotation(int(arg))]


class TransposeAnnotationParser(LaTeXAnnotationCommandParser):
    command_name = "transpose"

    def parse(self, arg: str) -> list[TransposeAnnotation]:
        return [TransposeAnnotation(int(arg))]


class PickAnnotationParser(LaTeXAnnotationCommandParser):
    command_name = "pick"

    def parse(self, arg: str) -> list[PickAnnotation]:
        return [PickAnnotation(arg)]


class MusicNoteAnnotationParser(LaTeXAnnotationCommandParser):
    command_name = "musicnote"

    def parse(self, arg: str) -> list[NoteAnnotation]:
        return [NoteAnnotation(arg)]


class ChordTabAnnotationParser(LaTeXAnnotationCommandParser):
    command_name = "showchordtab"
    arg_setting: ClassVar[CommandArgSetting] = CommandArgSetting(min_args=5, max_args=5, raw_args=(0, 1, 2, 3, 4))
    chord_parser: ChordParser = ModifiedSongsLatexChordParser()

    def parse(self, chord_mark: str, layout: str, width: str, hpos: str, vpos: str) -> list[ShowChordTab]:
        fret, positions, fingers = self._parse_layout(layout)
        return [
            ShowChordTab(
                chord=self.chord_parser.parse(chord_mark),
                fret=fret,
                positions=positions,
                fingers=fingers,
                width=float(width),
                hpos=float(hpos),
                vpos=float(vpos),
            )
        ]

    def _parse_layout(self, layout: str) -> tuple[int, StringPositions, StringPositions | None]:
        parts = layout.split(":")
        if len(parts) == 1:
            fret = 0
            positions = self._parse_string_positions(parts[0])
            fingers = None
        elif len(parts) == 2:
            if len(parts[0]) < 6:
                fret = int(parts[0])
                positions = self._parse_string_positions(parts[1])
                fingers = None
            else:
                fret = 0
                positions = self._parse_string_positions(parts[0])
                fingers = self._parse_string_positions(parts[1])
        elif len(parts) == 3:
            fret = int(parts[0])
            positions = self._parse_string_positions(parts[1])
            fingers = self._parse_string_positions(parts[2])
        else:
            raise ValueError(f"invalid showchordtab layout: {layout!r}")
        return fret, positions, fingers

    @staticmethod
    def _parse_string_positions(position_str: str) -> StringPositions:
        if len(position_str) != 6:
            raise ValueError(f"invalid guitar string positions: {position_str!r}, must have length exactly 6")
        chars = list(position_str)
        positions = tuple(int(char) if char.lower() != "x" else None for char in chars)
        return cast(StringPositions, positions)


@dataclasses.dataclass
class ModifiedSongsLaTeXFormat(SongFormat):
    name: ClassVar[str] = "latex-songs-modif"
    can_read: ClassVar[bool] = True
    can_write: ClassVar[bool] = True

    beginsong_pattern: re.Pattern[str] = re.compile(r"\s*\\beginsong\{(?P<title>[^}]+?)}(?:\[(?P<annots>[^]]+?)])?")
    beginsong_annot_pattern: re.Pattern[str] = re.compile(r"(?P<key>[a-z]+)=\{(?P<value>[^}]*?)}")
    beginsong_annot_keys: dict[str, type[Annotation]] = dataclasses.field(
        default_factory=lambda: {"by": AuthorAnnotation}
    )
    simple_beginverse_commands: dict[str, type[StropheMark] | functools.partial[StropheMark]] = dataclasses.field(
        default_factory=lambda: {
            "emptyv": EmptyStropheMark,
            "freev": EmptyStropheMark,
            "chor": ChorusMark,
            "intro": IntroMark,
            "solo": SoloMark,
            "bridge": BridgeMark,
            "chorusi": NumberedChorusMark(number=1),
            "chorusii": NumberedChorusMark(number=2),
            "averse": LetteredStropheMark(letter="A"),
            "bverse": LetteredStropheMark(letter="B"),
            "cverse": LetteredStropheMark(letter="C"),
            "recite": RecitationMark,
        }
    )
    numbered_beginverse_command: str = "num"
    endverse_commands: list[str] = dataclasses.field(default_factory=lambda: ["fin", "cl"])
    strophe_token_pattern: re.Pattern[str] = re.compile(r"([]\\[{}])")
    command_name_pattern: re.Pattern[str] = re.compile(r"\w+")
    whitespace_pattern: re.Pattern[str] = re.compile(r"\s+")
    chord_parser: ChordParser = dataclasses.field(default_factory=lambda: ModifiedSongsLatexChordParser())
    chord_level_commands: dict[int, str] = dataclasses.field(
        default_factory=lambda: {
            0: "{}",
            1: "\\hidx{{{}}}",
            -1: "\\didx{{{}}}",
        }
    )
    strophe_mark_commands: dict[StropheMark, str] = dataclasses.field(
        default_factory=lambda: {
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
    )
    text_load_repls: dict[str, str] = dataclasses.field(
        default_factory=lambda: {
            "~-- ": " - ",
            " -- ": " - ",
        }
    )
    text_load_patterns: dict[re.Pattern[str], str] = dataclasses.field(
        default_factory=lambda: {re.compile(r"\s+\n"): "\n"}
    )
    text_dump_repls: dict[str, str] = dataclasses.field(
        default_factory=lambda: {
            "\n": "\\\\\n",
            "...": "\\ldots{}",
            " - ": "~-- ",
        }
    )
    text_dump_patterns: dict[re.Pattern[str], str] = dataclasses.field(
        default_factory=lambda: {re.compile(r"\((?P<inner>[^\\)]+)\)"): r"\\emph{(\1)}"}
    )
    repcommands: dict[StropheMark, str] = dataclasses.field(
        default_factory=lambda: {
            ChorusMark(): "repchorus",
            NumberedChorusMark(number=1): "repchorusi",
            NumberedChorusMark(number=2): "repchorusii",
        }
    )
    no_chord_brace_length_multiple: float = 1.75
    no_chord_brace_length: int = 3
    segment_command_parsers: list[LaTeXSegmentCommandParser] = dataclasses.field(
        default_factory=lambda: [
            SimpleCommandParser(command_name="chordson", result=[TurnChordsOn()]),
            SimpleCommandParser(command_name="chordsoff", result=[TurnChordsOff()]),
            SimpleCommandParser(command_name="ldots", result=[IndeterminateChordingSegment("...")]),
            SimpleCommandParser(command_name="endsong", result=[]),
            SimpleCommandParser(command_name="emptyspace", result=[]),
            SimpleCommandParser(command_name=r"\\", result=[]),
            SimpleCommandParser(command_name="qquad", result=[]),
            PassthroughSegmentCommandParser(command_name="cseq"),
            PassthroughSegmentCommandParser(command_name="emph"),
            QuotesCommandParser(),
            RepeatCountCommandParser(),
            RepetitionCommandParser(),
            FixedEmbeddedAnnotationCommandParser(command_name="fadeout", annotation=FadeOutAnnotation()),
            StropheRepetitionCommandParser(),
        ]
    )
    annotation_command_parsers: list[LaTeXAnnotationCommandParser] = dataclasses.field(
        default_factory=lambda: [
            CapoAnnotationParser(),
            TransposeAnnotationParser(),
            PickAnnotationParser(),
            MusicNoteAnnotationParser(),
            ChordTabAnnotationParser(),
        ]
    )

    def __post_init__(self):
        super().__init__()
        for mark, command in self.strophe_mark_commands.items():
            self.segment_command_parsers.append(
                SimpleCommandParser(command_name=command, result=[EmbeddedStropheMark(mark)])
            )
        self.simple_beginverse_command_names = {v(): k for k, v in self.simple_beginverse_commands.items()}
        self.simple_beginverse_command_names[CodaMark()] = "cverse"
        self.beginverse_commands = [self.numbered_beginverse_command, *self.simple_beginverse_commands.keys()]
        self.strophe_split_pattern = re.compile(r"\\(?=(?:" + "|".join(self.beginverse_commands) + r")\b)")
        self.text_dump_repls |= {v: k for k, v in self.text_load_repls.items()}
        self.endverse_pattern: re.Pattern[str] = re.compile(r"\\(?:" + "|".join(self.endverse_commands) + r")\b")
        self.segment_command_parsers.extend(
            [
                FixedStropheMarkRepetitionCommandParser(command_name=cmd, mark=mark)
                for mark, cmd in self.repcommands.items()
            ]
        )
        self.command_parsers_by_name: dict[str, LaTeXSegmentCommandParser | LaTeXAnnotationCommandParser] = {
            cmd.command_name: cmd for cmd in (*self.segment_command_parsers, *self.annotation_command_parsers)
        }

    def loads(self, song_text: str) -> Song:
        annotations, remnant = self._parse_beginsong(song_text)
        strophe_strs = self.strophe_split_pattern.split(remnant)
        if len(strophe_strs) < 2:
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
        annotations: list[Annotation] = [TitleAnnotation(match.group("title"))]
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
                logging.warning(f"unknown \\beginsong annotation key: {key}={value}")
            other_annot_str = other_annot_str[annot_match.end() :]
        if other_annot_str:
            logging.warning(f"unprocessed \\beginsong content: {other_annot_str!r}")
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
            current_pos = self._skip_whitespace_and_comments(annot_str, pos=current_pos)
            if current_pos >= len(annot_str):
                break
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

    def _skip_whitespace_and_comments(self, text: str, pos: int) -> int:
        current_pos = pos
        while True:
            whitespace_match = self.whitespace_pattern.match(text[current_pos:])
            if whitespace_match:
                current_pos += len(whitespace_match.group())
            elif text[current_pos] == "%":
                current_pos = text.find("\n", current_pos) + 1
                if current_pos == 0:  # newline not found, assume end of string
                    return len(text)
            else:
                break
        return current_pos

    def _parse_strophe(
        self, strophe_str: str, num: int, chords_on: bool
    ) -> tuple[Strophe, list[EmbeddedStrophe | Annotation]]:
        mark_str = re.match(r"\w+", strophe_str).group()
        mark = self._parse_strophe_mark(mark_str, num=num)
        parts = self.endverse_pattern.split(strophe_str[len(mark_str) :])
        if len(parts) != 2:
            raise SongParseError("mismatched strophe start/end commands")
        body, afterpart = [part.strip() for part in parts]
        strophe_segments = self._parse_strophe_segments(body, chords_on=chords_on)
        strophe_segments, inner_annotations = self._extract_strophe_annotations(strophe_segments)
        strophe = Strophe(mark=mark, segments=strophe_segments)
        return strophe, inner_annotations + self._parse_annotation_chunk(afterpart)

    @staticmethod
    def _extract_strophe_annotations(
        segments: list[StropheSegment | ProcessingInstruction],
    ) -> tuple[list[StropheSegment], list[Annotation]]:
        segments = segments.copy()
        annotations: list[Annotation] = []
        i = 0
        while i < len(segments):
            if isinstance(segments[i], EmbeddedAnnotation):
                annotations.append(segments.pop(i).annotation)
            else:
                i += 1
        return segments, annotations

    def _parse_strophe_mark(self, mark_str: str, num: int) -> StropheMark:
        if mark_str == self.numbered_beginverse_command:
            return NumberedStropheMark(num)
        elif mark_str in self.simple_beginverse_commands:
            return self.simple_beginverse_commands[mark_str]()
        else:
            raise SongParseError(f"unknown strophe mark command: {mark_str!r}")

    def _parse_strophe_segments(self, body: str, chords_on: bool) -> list[StropheSegment | ProcessingInstruction]:
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
    def _join_strophe_segments(  # noqa: C901  # no time
        cls, segments: list[StropheSegment | ProcessingInstruction], chords_on: bool
    ) -> list[StropheSegment | ProcessingInstruction]:
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
                    n_repeats=segments[seg_i].n_repeats,
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
                move = 1
                for j in range(1, seg_i + 1):
                    if isinstance(segments[seg_i - j], Repetition):
                        segments[seg_i - j].n_repeats = segments[seg_i].n_repeats
                        for k in range(j):
                            # Remove all intervening empty space segments.
                            segments.pop(seg_i - k)
                            move -= 1
                        break
                    elif not isinstance(segments[seg_i - j], ChordlessSegment) or segments[seg_i - j].text.strip():
                        # Skip through empty space segments when finding a corresponding repetition segment.
                        break
                seg_i += move
            else:
                seg_i += 1
        return segments

    def _parse_strophe_part(self, text: str, pos: int) -> tuple[list[StropheSegment | ProcessingInstruction], int]:
        if text[pos] == "\\" and text[pos : pos + 2] != "\\[":
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
        if command_name not in self.command_parsers_by_name:
            raise PositionalSongParseError(f"unknown command: {command_name!r}", text, pos)
        parser = self.command_parsers_by_name[command_name]
        args, after_pos = self._parse_command_args(text, post_command_name_pos, setting=parser.arg_setting)
        if not args:
            # skip whitespace after command name if no braces present
            after_pos = post_command_name_pos + (
                len(text[post_command_name_pos:]) - len(text[post_command_name_pos:].lstrip())
            )
        return parser.parse(*args), after_pos

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
            if not all(isinstance(part, ChordlessSegment) for part in inner_chunk):
                raise PositionalSongParseError("non-plain chord scope parentheses content", text, after_chord_pos)
            inner_text = "".join(part.text for part in inner_chunk)
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
        while text.count("{", current_pos, end_pos) > text.count("}", current_pos, end_pos):
            # Ignore any nested curly braces.
            end_pos = text.find("}", end_pos + 1)
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
    def _parse_repsec_marked(
        segs: list[StropheSegment | ProcessingInstruction], mark: StropheMark
    ) -> list[EmbeddedStrophe]:
        if segs and isinstance(segs[-1], RepeatCount):
            n_repeats = segs[-1].n_repeats
            segs.pop()
        else:
            n_repeats = 1
        emb_strophe = EmbeddedStrophe(RepeatStropheWithSameMark(mark=mark, segments=segs))
        return [emb_strophe] * n_repeats

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

    def dump_endsong(self, song: Song) -> str:  # noqa: ARG002 # format compatibility
        return "\\endsong"

    def dump_annotations(self, song: Song, chords: bool = True) -> str:
        rem_annots = song.get_displayable_annotations(chords=chords)
        if not rem_annots:
            return ""
        return "\n".join(self.dump_annotation(annot) for annot in rem_annots)

    def dump_annotation(self, annot: Annotation) -> str:
        if isinstance(annot, CapoAnnotation):
            return f"\\capo{{{annot.fret}}}"
        elif isinstance(annot, TransposeAnnotation):
            return f"\\transpose{{{annot.fret}}}"
        elif isinstance(annot, PickAnnotation):
            return f"\\pick{{{annot.pattern}}}"
        elif isinstance(annot, NoteAnnotation):
            return f"\\musicnote{{{annot.text}}}"
        elif isinstance(annot, FadeOutAnnotation):
            return "\\freev\\fadeout\\emptyspace\\\\cl\n"
        elif isinstance(annot, ShowChordTab):
            # \showchordtab{C/G}{332010:342010}{1.5}{10}{4}
            return (
                f"\\showchordtab{{{self.dump_chord(annot.chord)}}}{{{annot.layout_str}}}"
                f"{{{annot.width}}}{{{annot.hpos}}}{{{annot.vpos}}}"
            )
        elif isinstance(annot, TurnChordsOff):
            return ""  # done automatically, always
        raise TypeError(f"unknown annotation type: {annot!r}")

    def dump_song_items(self, song: Song, chords: bool) -> Generator[str, None, None]:
        accummulated_repeats = []
        for i, item in enumerate(song.items):
            if isinstance(item, Annotation) and (chords or not item.is_chord_annotation):
                yield self.dump_annotation(item)
            elif isinstance(item, SimpleStropheRepeat):
                accummulated_repeats.append(item)
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
        inner = self.dump_segments(strophe.segments, chords=chords)
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
        if chords and segments and isinstance(segments[0], ChordedSegment | UnknownChordSegment):
            if all(isinstance(seg, ChordedSegment) and (not seg.text or seg.text.isspace()) for seg in segments):
                return self.dump_cseq(segments)
            dumped.append("\\chordson\n")
        prev_seg = None
        for seg in segments:
            dumped.extend(self.dump_segment(seg, chords=chords, prev_seg=prev_seg))
            prev_seg = seg
        return "".join(dumped).replace("\n\n", "\n")

    def dump_segment(self, seg: StropheSegment, chords: bool, prev_seg: StropheSegment | None):  # noqa: C901 # no time
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
        elif isinstance(seg, UnchordedSegment | UnknownChordSegment) or (
            isinstance(seg, ChordedSegment) and not chords
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
            if inner.startswith("\\chordson"):
                inner = inner.removeprefix("\\chordson").lstrip()
                yield "\\chordson"
            yield f"\\reppart{{{inner}}}"
            if seg.n_repeats > 2:
                yield f" \\rep{{{seg.n_repeats}}}"
        elif isinstance(seg, EmbeddedAnnotation) and isinstance(seg.annotation, FadeOutAnnotation):
            yield "\\fadeout"
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
        for modif in chord.modifiers:
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


if __name__ == "__main__":
    from pathlib import Path
    import pprint

    chords_path = Path(__file__).parent.parent / "test" / "data"
    in_out_format = ModifiedSongsLaTeXFormat()
    for path in chords_path.iterdir():
        if path.suffix == ".tex" and "berousek" in str(path):
            text = path.open(encoding="utf8").read()
            print(text)  # noqa: T201
            song = NORMALIZER.modify(in_out_format.loads(text))
            pprint.pprint(song)  # noqa: T203
            result = in_out_format.dumps(song, chords=True)
            print(result)  # noqa: T201

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
