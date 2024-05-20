import abc
import copy
from abc import ABC
import dataclasses
from typing import ClassVar, Literal, Type, TypeVar


# TODO CZ/EN note convention
Note = Literal["C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Fb", "G", "G#", "Gb", "A", "A#", "Ab", "B", "H"]


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

    @abc.abstractmethod
    def splitlines(self) -> list["StropheSegment"]:
        raise NotImplementedError


@dataclasses.dataclass
class PlainSegment(StropheSegment):
    text: str = ""  # needs default value to override abstract property

    def __add__(self, other: str) -> "PlainSegment":
        return PlainSegment(text=self.text + other)

    def __sub__(self, other: str) -> "PlainSegment":
        return PlainSegment(text=self.text.removesuffix(other))

    def splitlines(self) -> list["PlainSegment"]:
        text_chunks = self.text.split("\n")
        segments = [PlainSegment(chunk + "\n") for chunk in text_chunks[:-1]]
        if text_chunks[-1]:
            segments.append(PlainSegment(text_chunks[-1]))
        return segments


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
class AddedNote(ChordModifier):
    factor: int
    level: ClassVar[int] = 1

    def to_string(self) -> str:
        return str(self.factor)


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

    def __add__(self, other: str) -> "ChordedSegment":
        return ChordedSegment(chord=self.chord, text=self.text + other)

    def __sub__(self, other: str) -> "ChordedSegment":
        return ChordedSegment(chord=self.chord, text=self.text.removesuffix(other))

    def splitlines(self) -> list["ChordedSegment"]:
        plain_split = PlainSegment(self.text).splitlines()
        if not plain_split:
            return [self]
        return [self.__class__(chord=self.chord, text=plseg.text) for plseg in plain_split]


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

    def to_string(self, short: bool) -> str:
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

    def to_string(self, short: bool) -> str:
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
    def from_string(cls, mark: str) -> "InvariantStropheMark":
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

    def to_string(self, short: bool) -> str:
        return "Intro"


class BridgeMark(InvariantStropheMark):
    is_chorus: ClassVar[bool] = False

    def to_string(self, short: bool) -> str:
        return "M" if short else "Bridge"


class SoloMark(InvariantStropheMark):
    is_chorus: ClassVar[bool] = False

    def to_string(self, short: bool) -> str:
        return "Solo"


class RecitationMark(InvariantStropheMark):
    is_chorus: ClassVar[bool] = False

    def to_string(self, short: bool) -> str:
        return "Rec"


class CodaMark(InvariantStropheMark):
    is_chorus: ClassVar[bool] = False

    def to_string(self, short: bool) -> str:
        return "C" if short else "Coda"


class EmptyStropheMark(InvariantStropheMark):
    is_chorus: ClassVar[bool] = False

    def to_string(self, short: bool) -> str:
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
    repeated_strophe: Strophe

    def __init__(self, repeated_strophe: Strophe):
        self.repeated_strophe = repeated_strophe

    @property
    def mark(self) -> StropheMark:
        return self.repeated_strophe.mark

    @property
    def segments(self) -> list[StropheSegment]:
        return self.repeated_strophe.segments  # TODO this brings up some trouble


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

    def get_annotations_of_type(self, annot_type: Type[A]) -> list[A]:
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

    def normalized(self) -> "Song":
        return Song(
            annotations=copy.deepcopy(self.annotations),
            items=self.link_strophe_repeats(copy.deepcopy(self.items)),
        )

    def link_strophe_repeats(self, items: list[Strophe | Annotation]) -> list[Strophe | Annotation]:
        linked_items = []
        for i, item in enumerate(items):
            if isinstance(item, RepeatStropheWithSameMark):
                if item.segments:
                    raise NotImplementedError("cannot link strophe repeats with modifications")
                for j, link_item in reversed(list(enumerate(items[:i]))):
                    if isinstance(link_item, Strophe) and link_item.mark == item.mark:
                        linked_items.append(StropheRepeat(repeated_strophe=link_item))
                        break
                else:
                    raise ValueError(f"cannot find strophe of mark {item.mark} to repeat")
            else:
                linked_items.append(item)
        return linked_items
