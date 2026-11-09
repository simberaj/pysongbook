import abc
from abc import ABC
import dataclasses
from functools import cached_property
import typing
from typing import ClassVar, Literal, Self, TypeAlias, TypeVar


# TODO CZ/EN note convention
StringPositions: TypeAlias = tuple[int | None, int | None, int | None, int | None, int | None, int | None]
Note = Literal["C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Fb", "G", "G#", "Gb", "A", "A#", "Ab", "B", "Bb", "H"]
NOTES = typing.get_args(Note)


class MalformedSongError(ValueError):
    pass


class StropheSegment(ABC):
    @abc.abstractmethod
    def __add__(self, other: str):
        raise NotImplementedError

    @abc.abstractmethod
    def __sub__(self, other: str):
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def text(self) -> str:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def raw_text(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def splitlines(self) -> list["StropheSegment"]:
        raise NotImplementedError


@dataclasses.dataclass
class ChordlessSegment(StropheSegment):
    """A segment without annotating chords: either there are none, or they need to be inferred from context."""

    text: str = ""  # needs default value to override abstract property

    def __add__(self, other: str) -> Self:
        return self.__class__(text=self.text + other)

    def __sub__(self, other: str) -> Self:
        return self.__class__(text=self.text.removesuffix(other))

    def splitlines(self) -> list[Self]:
        text_chunks = self.text.split("\n")
        segments = [self.__class__(text=chunk + "\n") for chunk in text_chunks[:-1]]
        if text_chunks[-1]:
            segments.append(self.__class__(text=text_chunks[-1]))
        return segments

    @property
    def raw_text(self) -> str:
        return self.text


class UnchordedSegment(ChordlessSegment):
    """A segment which does not and is not meant to have a chord."""


class IndeterminateChordingSegment(ChordlessSegment):
    """A segment which might or might not have a chord."""


class UnknownChordSegment(ChordlessSegment):
    """A segment whose chord is not known yet should have one, and should be inferred from the context."""


class ChordModifier(ABC):
    @property
    @abc.abstractmethod
    def level(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def to_string(self) -> str:
        raise NotImplementedError


@dataclasses.dataclass
class Minor(ChordModifier):
    level: ClassVar[int] = 0

    def to_string(self) -> str:
        return "m"


@dataclasses.dataclass
class DominantSeventh(ChordModifier):
    level: ClassVar[int] = 1

    def to_string(self) -> str:
        return "7"


@dataclasses.dataclass
class MajorSeventh(ChordModifier):
    level: ClassVar[int] = 1

    def to_string(self) -> str:
        return "maj7"


@dataclasses.dataclass
class HigherNote(ChordModifier):
    factor: int
    level: ClassVar[int] = 1
    allowed_factors: ClassVar[list[int]] = [6, 9, 11, 13]

    def to_string(self) -> str:
        return str(self.factor)


@dataclasses.dataclass
class AddedNote(ChordModifier):
    factor: int
    level: ClassVar[int] = 1

    def to_string(self) -> str:
        return f"add{self.factor}"


@dataclasses.dataclass
class Suspended(ChordModifier):
    factor: int
    level: ClassVar[int] = 1

    def to_string(self) -> str:
        return f"sus{self.factor}"


@dataclasses.dataclass
class Altered(ChordModifier):
    direction: Literal["+", "dim"]
    factor: int = 5
    level: ClassVar[int] = 1

    def to_string(self) -> str:
        return self.direction if self.factor == 5 else f"{self.direction}{self.factor}"


@dataclasses.dataclass
class BassNote(ChordModifier):
    note: Note
    level: ClassVar[int] = 0

    def to_string(self) -> str:
        return "/" + self.note


@dataclasses.dataclass
class GenericChordModifier(ChordModifier):  # todo replace with meaningful ChordModifiers
    string: str
    level: ClassVar[int] = 1

    def to_string(self) -> str:
        return self.string


@dataclasses.dataclass
class Chord:
    root: Note
    modifiers: list[ChordModifier]

    def to_string(self) -> str:
        return self.root + "".join(modif.to_string() for modif in self.modifiers)


@dataclasses.dataclass
class ChordedSegment(StropheSegment):
    chord: Chord
    text: str = ""  # needs default value to override abstract property

    def __add__(self, other: str) -> Self:
        return self.__class__(chord=self.chord, text=self.text + other)

    def __sub__(self, other: str) -> Self:
        return self.__class__(chord=self.chord, text=self.text.removesuffix(other))

    def splitlines(self) -> list[Self]:
        plain_split = UnchordedSegment(self.text).splitlines()
        if not plain_split:
            return [self]
        return [self.__class__(chord=self.chord, text=plseg.text) for plseg in plain_split]

    @property
    def raw_text(self) -> str:
        return self.text


class BaseStropheSegmentCollection(StropheSegment, ABC):
    """A base class for nested strophe segments (segments that contain other segments)."""

    segments: list[StropheSegment]


@dataclasses.dataclass
class Repetition(BaseStropheSegmentCollection):
    """A section of a strophe that is meant to be repeated multiple times."""

    segments: list[StropheSegment]
    n_repeats: int = 2

    def __add__(self, other: str) -> Self:
        return self.__class__(segments=self.segments[:-1] + [self.segments[-1] + other], n_repeats=self.n_repeats)

    def __sub__(self, other: str) -> Self:
        return self.__class__(segments=self.segments[:-1] + [self.segments[-1] - other], n_repeats=self.n_repeats)

    @property
    def text(self) -> str:
        # return "".join(seg.text for seg in self.segments)
        raise ValueError("cannot get text of repetition")

    @property
    def raw_text(self) -> str:
        return "".join(seg.raw_text for seg in self.segments)

    def splitlines(self) -> list[Self]:
        return [
            self.__class__(
                segments=[subseg for seg in self.segments for subseg in seg.splitlines()], n_repeats=self.n_repeats
            )
        ]


def start_has_chords_on(segments: list[StropheSegment]) -> bool:
    if not segments:
        raise ValueError("empty segments")
    first_segment = segments[0]
    if isinstance(first_segment, BaseStropheSegmentCollection):
        if not first_segment.segments:
            return start_has_chords_on(segments[1:])
        return start_has_chords_on(first_segment.segments)
    return isinstance(first_segment, ChordedSegment | UnknownChordSegment)


def end_has_chords_on(segments: list[StropheSegment]) -> bool:
    if not segments:
        raise ValueError("empty segments")
    last_segment = segments[-1]
    if isinstance(last_segment, BaseStropheSegmentCollection):
        if not last_segment.segments:
            return start_has_chords_on(segments[:-1])
        return end_has_chords_on(last_segment.segments)
    return isinstance(last_segment, ChordedSegment | UnknownChordSegment)


def all_have_chords_on(segments: list[StropheSegment]) -> bool:
    if not segments:
        raise ValueError("empty segments")
    for seg in segments:
        if isinstance(seg, BaseStropheSegmentCollection):
            if not all_have_chords_on(seg.segments):
                return False
        elif not isinstance(seg, ChordedSegment | UnknownChordSegment):
            return False
    return True


# Removed because determining repeated strophe parts is not meaningfully possible.
# @dataclasses.dataclass
# class RepeatedStrophePart(BaseStropheSegmentCollection):
#     """A part of a strophe repeat that is identical to the repeated strophe (unmodified)."""
#
#     segments: list[StropheSegment]
#
#     def __add__(self, other: str) -> Self:
#         return self.__class__(segments=self.segments[:-1] + [self.segments[-1] + other])
#
#     def __sub__(self, other: str) -> Self:
#         return self.__class__(segments=self.segments[:-1] + [self.segments[-1] - other])
#
#     @property
#     def text(self) -> str:
#         return "".join(seg.text for seg in self.segments)
#
#     def splitlines(self) -> list[Self]:
#         return [self.__class__(segments=[subseg for seg in self.segments for subseg in seg.splitlines()])]


class StropheMark(ABC):
    @classmethod
    @abc.abstractmethod
    def from_string(cls, mark: str) -> "StropheMark":
        raise NotImplementedError

    @abc.abstractmethod
    def to_string(self, short: bool) -> str:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def is_chorus(self) -> bool:
        raise NotImplementedError


@dataclasses.dataclass(eq=True, frozen=True)
class NumberedStropheMark(StropheMark):
    number: int
    is_chorus: ClassVar[bool] = False

    @classmethod
    def from_string(cls, mark: str) -> "NumberedStropheMark":
        return cls(int(mark))

    def to_string(self, short: bool) -> str:  # noqa: ARG002 # short and long form the same
        return str(self.number)


@dataclasses.dataclass(eq=True, frozen=True)
class LetteredStropheMark(StropheMark):
    letter: Literal["A", "B", "C", "D", "E"]
    is_chorus: ClassVar[bool] = False

    @classmethod
    def from_string(cls, mark: str) -> "LetteredStropheMark":
        if mark not in ["A", "B", "C", "D", "E"]:
            raise ValueError("invalid lettered strophe mark")
        return cls(mark)

    def to_string(self, short: bool) -> str:  # noqa: ARG002 # short and long form the same
        return self.letter


@dataclasses.dataclass(eq=True, frozen=True)
class NumberedChorusMark(StropheMark):
    number: int
    is_chorus: ClassVar[bool] = True

    @classmethod
    def from_string(cls, mark: str) -> "NumberedChorusMark":
        return cls(int(mark.lstrip("R")))

    def to_string(self, short: bool) -> str:
        return f"R{self.number}" if short else f"Chorus {self.number}"


@dataclasses.dataclass(eq=True, frozen=True)  # makes all instances of the same class equal (no attrs)
class InvariantStropheMark(StropheMark):
    @classmethod
    def from_string(cls, mark: str) -> "InvariantStropheMark":  # noqa: ARG003 # class defines the mark
        return cls()

    @abc.abstractmethod
    def to_string(self, short: bool) -> str:
        pass


class ChorusMark(InvariantStropheMark):
    is_chorus: ClassVar[bool] = True

    def to_string(self, short: bool) -> str:
        return "R" if short else "Chorus"


class IntroMark(InvariantStropheMark):
    is_chorus: ClassVar[bool] = False

    def to_string(self, short: bool) -> str:  # noqa: ARG002 # short and long form the same
        return "Intro"


class BridgeMark(InvariantStropheMark):
    is_chorus: ClassVar[bool] = False

    def to_string(self, short: bool) -> str:
        return "M" if short else "Bridge"


class SoloMark(InvariantStropheMark):
    is_chorus: ClassVar[bool] = False

    def to_string(self, short: bool) -> str:  # noqa: ARG002 # short and long form the same
        return "Solo"


class RecitationMark(InvariantStropheMark):
    is_chorus: ClassVar[bool] = False

    def to_string(self, short: bool) -> str:
        return "Rec" if short else "Recitation"


class CodaMark(InvariantStropheMark):
    is_chorus: ClassVar[bool] = False

    def to_string(self, short: bool) -> str:
        return "C" if short else "Coda"


class EmptyStropheMark(InvariantStropheMark):
    is_chorus: ClassVar[bool] = False

    def to_string(self, short: bool) -> str:  # noqa: ARG002 # short and long form the same
        return ""


@dataclasses.dataclass
class Strophe:
    mark: StropheMark
    segments: list[StropheSegment]

    def single_line_segments(self) -> list[StropheSegment]:
        return [chunk for seg in self.segments for chunk in seg.splitlines()]


class RepeatStropheWithSameMark(Strophe):
    """A strophe that repeats some undefined previous strophe, to be determined by the strophe mark."""


@dataclasses.dataclass
class StropheRepeat(Strophe):
    """A strophe that repeats a previous strophe."""

    repeated_strophe: Strophe

    @property
    def mark(self) -> StropheMark:
        return self.repeated_strophe.mark


@dataclasses.dataclass
class SimpleStropheRepeat(StropheRepeat):
    """A strophe that repeats a previous strophe without any modification."""

    def __init__(self, repeated_strophe: Strophe):
        self.repeated_strophe = repeated_strophe

    @property
    def segments(self) -> list[StropheSegment]:
        return self.repeated_strophe.segments  # TODO this brings up some trouble


@dataclasses.dataclass
class ModifiedStropheRepeat(StropheRepeat):
    """A strophe that repeats a previous strophe, but with modified segments."""

    def __init__(self, repeated_strophe: Strophe, segments: list[StropheSegment]):
        self.repeated_strophe = repeated_strophe
        self.segments = segments


class Annotation(ABC):
    @property
    @abc.abstractmethod
    def is_chord_annotation(self) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def to_string(self, delimiter: str) -> str:
        raise NotImplementedError


@dataclasses.dataclass
class AuthorAnnotation(Annotation):
    name: str
    is_chord_annotation: ClassVar[bool] = False

    def to_string(self, delimiter: str) -> str:
        return "Author" + delimiter + self.name


@dataclasses.dataclass
class TitleAnnotation(Annotation):
    title: str
    is_chord_annotation: ClassVar[bool] = False

    def to_string(self, delimiter: str) -> str:
        return "Title" + delimiter + self.title


@dataclasses.dataclass
class CapoAnnotation(Annotation):
    fret: int
    is_chord_annotation: ClassVar[bool] = True

    def to_string(self, delimiter: str) -> str:
        return "Capo" + delimiter + str(self.fret)


@dataclasses.dataclass
class TransposeAnnotation(Annotation):
    fret: int
    is_chord_annotation: ClassVar[bool] = True

    def to_string(self, delimiter: str) -> str:
        return "Transpose" + delimiter + str(self.fret)


@dataclasses.dataclass
class PickAnnotation(Annotation):
    pattern: str
    is_chord_annotation: ClassVar[bool] = True

    def to_string(self, delimiter: str) -> str:
        return "Pick" + delimiter + self.pattern


@dataclasses.dataclass
class NoteAnnotation(Annotation):
    text: str
    is_chord_annotation: ClassVar[bool] = False

    def to_string(self, delimiter: str) -> str:
        return "Note" + delimiter + self.text


@dataclasses.dataclass
class FadeOutAnnotation(Annotation):
    is_chord_annotation: ClassVar[bool] = False

    def to_string(self, delimiter: str) -> str:
        return f"Ending{delimiter}to fade out"


@dataclasses.dataclass
class Comment(Annotation):
    text: str
    is_chord_annotation: ClassVar[bool] = False

    def to_string(self, delimiter: str) -> str:
        return "Comment" + delimiter + self.text


@dataclasses.dataclass
class ShowChordTab(Annotation):
    chord: Chord
    fret: int
    positions: StringPositions
    fingers: StringPositions | None
    width: float
    hpos: float
    vpos: float
    is_chord_annotation: ClassVar[bool] = True

    @cached_property
    def layout_str(self) -> str:
        layout_str = string_positions_to_string(self.positions)
        if self.fret > 0:
            layout_str = f"{self.fret}:{layout_str}"
        if self.fingers is not None:
            layout_str += ":" + string_positions_to_string(self.fingers)
        return layout_str

    def to_string(self, delimiter: str) -> str:
        return self.chord.to_string() + delimiter + self.layout_str


def string_positions_to_string(positions: StringPositions) -> str:
    return "".join(str(pos) if pos is not None else "X" for pos in positions)


@dataclasses.dataclass
class GenericAnnotation(Annotation):  # TODO this should be replaced by more specialized subclasses & left as fallback
    key: str
    value: str
    is_chord_annotation: bool = False

    def to_string(self, delimiter: str) -> str:
        return self.key + delimiter + self.value


A = TypeVar("A", bound=Annotation)


@dataclasses.dataclass
class Song:
    annotations: list[Annotation]
    items: list[Strophe | Annotation]  # TODO allow only some annotations between strophes?

    def get_annotations_of_type(self, annot_type: type[A]) -> list[A]:
        return [annot for annot in self.annotations if isinstance(annot, annot_type)]

    def get_title(self) -> str | None:
        titles = [annot.title for annot in self.get_annotations_of_type(TitleAnnotation)]
        if not titles:
            return None
        elif len(titles) > 1:
            raise MalformedSongError("multiple song titles")
        else:
            return titles[0]

    def get_displayable_annotations(
        self,
        exclude_types: frozenset[type[Annotation]] = frozenset([TitleAnnotation, AuthorAnnotation]),
        chords: bool = True,
    ) -> list[Annotation]:
        return [
            annot
            for annot in self.annotations
            if not isinstance(annot, tuple(exclude_types)) and (chords or not annot.is_chord_annotation)
        ]
