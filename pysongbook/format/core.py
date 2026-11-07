import abc
from abc import ABC
import dataclasses
import json

from pysongbook.model import Annotation, Song, Strophe, StropheMark, StropheSegment


class SongParseError(ValueError):
    pass


class PositionalSongParseError(ValueError):
    def __init__(self, issue: str, text: str, pos: int):
        self.issue = issue
        self.pos = pos
        super().__init__(f"{issue} around {text[pos - 10 : pos + 10]!r} at {text[pos : pos + 10]!r} (index {pos})")


class ProcessingInstruction(Annotation):
    is_chord_annotation = False

    def to_string(self, delimiter: str) -> str:  # noqa: ARG002  # interface compatibility
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
class EmbeddedAnnotation(ProcessingInstruction):
    annotation: Annotation


@dataclasses.dataclass
class RepeatCount(ProcessingInstruction):
    n_repeats: int


class ModelDictFormat(SongFormat):
    name = "dict"
    can_read = False
    can_write = True

    def dumps(self, song: Song) -> str:
        return json.dumps(dataclasses.asdict(song))


@dataclasses.dataclass
class CommandArgSetting:
    min_args: int = 0
    max_args: int = 1
    raw_args: list[int] = dataclasses.field(default_factory=list)


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
