import abc
from abc import ABC
import dataclasses
from typing import Literal, Type, TypeVar


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


@dataclasses.dataclass
class PlainSegment(StropheSegment):
    text: str = ""  # needs default value to override abstract property

    def __add__(self, other: str) -> "PlainSegment":
        return PlainSegment(text=self.text + other)

    def __sub__(self, other: str) -> "PlainSegment":
        return PlainSegment(text=self.text.removesuffix(other))


class ChordModifier(ABC):
    @abc.abstractmethod
    def to_string(self) -> str:
        raise NotImplementedError


@dataclasses.dataclass
class GenericChordModifier(ChordModifier):  # todo replace with meaningful ChordModifiers
    string: str

    def to_string(self) -> str:
        return self.string


@dataclasses.dataclass
class Chord:
    # major: Literal["A", "B", "C", "D", "E", "F", "G"]  # TODO also halftones!
    root: str
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


class StropheMark(ABC):
    @classmethod
    @abc.abstractmethod
    def from_string(cls, mark: str) -> "StropheMark":
        raise NotImplementedError

    @abc.abstractmethod
    def to_string(self, short: bool) -> str:
        raise NotImplementedError


@dataclasses.dataclass
class NumberedStropheMark(StropheMark):
    number: int

    @classmethod
    def from_string(cls, mark: str) -> "NumberedStropheMark":
        return cls(int(mark))

    def to_string(self, short: bool) -> str:
        return str(self.number)


@dataclasses.dataclass
class LetteredStropheMark(StropheMark):
    letter: Literal["A", "B", "C", "D", "E"]

    @classmethod
    def from_string(cls, mark: str) -> "LetteredStropheMark":
        if mark not in ["A", "B", "C", "D", "E"]:
            raise ValueError("invalid lettered strophe mark")
        return cls(mark)

    def to_string(self, short: bool) -> str:
        return self.letter


class InvariantStropheMark(StropheMark):
    @classmethod
    def from_string(cls, mark: str) -> "InvariantStropheMark":
        return cls()

    @abc.abstractmethod
    def to_string(self, short: bool) -> str:
        pass


class ChorusMark(InvariantStropheMark):
    def to_string(self, short: bool) -> str:
        return "R" if short else "Chorus"


class CodaMark(InvariantStropheMark):
    def to_string(self, short: bool) -> str:
        return "C" if short else "Coda"


class EmptyStropheMark(InvariantStropheMark):
    def to_string(self, short: bool) -> str:
        return ""


@dataclasses.dataclass
class Strophe:
    mark: StropheMark
    segments: list[StropheSegment]


class Annotation(ABC):
    @abc.abstractmethod
    def to_string(self, delimiter: str) -> str:
        raise NotImplementedError


@dataclasses.dataclass
class AuthorAnnotation(Annotation):
    name: str

    def to_string(self, delimiter: str) -> str:
        return "Author" + delimiter + self.name


@dataclasses.dataclass
class TitleAnnotation(Annotation):
    title: str

    def to_string(self, delimiter: str) -> str:
        return "Title" + delimiter + self.title


@dataclasses.dataclass
class GenericAnnotation(Annotation):  # TODO this should be replaced by more specialized subclasses (left as fallback)
    key: str
    value: str

    def to_string(self, delimiter: str) -> str:
        return self.key + delimiter + self.value


A = TypeVar("A", bound=Annotation)


@dataclasses.dataclass
class Song:
    annotations: list[Annotation]
    items: list[Strophe | Annotation]  # TODO allow only some annotations between strophes?

    def get_annotations_of_type(self, annot_type: Type[A]) -> list[A]:
        return [annot for annot in self.annotations if isinstance(annot, annot_type)]
