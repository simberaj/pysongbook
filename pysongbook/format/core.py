import abc
from abc import ABC
from collections.abc import Iterable
import dataclasses
import json
from typing import NoReturn

from pysongbook.index import SongIndex
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

    @property
    def string(self) -> NoReturn:
        raise ValueError(f"cannot serialize processing instruction {self}")


class TurnChordsOn(ProcessingInstruction):
    pass


class TurnChordsOff(ProcessingInstruction):
    pass


class SongFormat(ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    other_names: tuple[str, ...] = ()

    @property
    @abc.abstractmethod
    def can_read(self) -> bool: ...

    def load_song(self, song_text: str) -> Song:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def can_write(self) -> bool: ...

    def dump_song(self, song: Song) -> str:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def can_split(self) -> bool: ...

    def split(self, multisong_text: str) -> list[str]:
        raise NotImplementedError

    @abc.abstractmethod
    def dump_index(self, index: SongIndex, identifier: str) -> dict[str | None, str]:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def can_merge(self) -> bool: ...

    def merge_songs(self, song_texts: Iterable[str], standalone: bool) -> str:
        del standalone
        return "\n\n".join(song_texts)

    def merge_indices(self, index_texts: Iterable[str]) -> str:
        return "\n".join(index_texts)

    def make_standalone(self, song_content: str, index_content: str = "", title_content: str = "") -> str:
        if index_content or title_content:
            return f"{title_content}\n{index_content}\n{song_content}"
        return song_content


@dataclasses.dataclass
class EmbeddedStrophe(StropheSegment):
    strophe: Strophe

    def __add__(self, other: str):
        raise ValueError(f"cannot merge embedded strophe with {other!r}")

    def __sub__(self, other: str):
        raise ValueError(f"cannot subtract {other!r} from embedded strophe")

    @property
    def raw_text(self) -> str:
        raise NotImplementedError

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
    can_merge = False
    can_split = False

    def dump_song(self, song: Song) -> str:
        return json.dumps(dataclasses.asdict(song))


@dataclasses.dataclass(frozen=True)
class CommandArgSetting:
    min_args: int = 0
    max_args: int = 1
    raw_args: tuple[int, ...] = ()


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
