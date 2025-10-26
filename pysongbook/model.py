import abc
import collections
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
        return [type(self)(chord=self.chord, text=plseg.text) for plseg in plain_split]


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
            items=self._fill_initial_plain_segments(self._recognize_codas(self._infer_chorus_repetition(self._link_strophe_repeats(copy.deepcopy(self.items))))),
        )

    @staticmethod
    def _link_strophe_repeats(items: list[Strophe | Annotation]) -> list[Strophe | Annotation]:
        linked_items = []
        for i, item in enumerate(items):
            if isinstance(item, RepeatStropheWithSameMark):
                for j, link_item in reversed(list(enumerate(items[:i]))):
                    if isinstance(link_item, Strophe) and link_item.mark == item.mark:
                        break
                else:
                    raise ValueError(f"cannot find strophe of mark {item.mark} to repeat")
                if item.segments:
                    first_segment_text = item.segments[0].text
                    for i, seg in enumerate(link_item.segments):
                        if first_segment_text in seg.text:
                            break
                    break_segment = dataclasses.replace(seg, text=seg.text[:seg.text.find(first_segment_text)])
                    result_segments = link_item.segments[:i] + [break_segment] + item.segments
                    result_item = Strophe(mark=item.mark, segments=result_segments)
                else:
                    result_item = StropheRepeat(repeated_strophe=link_item)
                linked_items.append(result_item)
            else:
                linked_items.append(item)
        return linked_items

    @staticmethod
    def _infer_chorus_repetition(items: list[Strophe | Annotation]) -> list[Strophe | Annotation]:
        strophe_types = [type(item.mark) for item in items if isinstance(item, Strophe)]
        if len(strophe_types) <= 2 or len(strophe_types) < len(items):
            return items
        type_pattern = [NumberedStropheMark, ChorusMark] + [NumberedStropheMark] * (len(strophe_types) - 2)
        if strophe_types == type_pattern:
            # Inlay chorus repetition after the second and each subsequent strophe.
            repeat_chorus = StropheRepeat(items[1])
            inlaid = items[:2] + [item for strophe in items[2:] for item in (strophe, repeat_chorus)]
            return inlaid
        return items

    @staticmethod
    def _fill_initial_plain_segments(items: list[Strophe | Annotation]) -> list[Strophe | Annotation]:
        replacements = []
        strophes: list[tuple[int, Strophe]] = [(i, item) for i, item in enumerate(items) if isinstance(item, Strophe)]
        for prev, current in zip(strophes[:-1], strophes[1:]):
            prev_i, prev_strophe = prev
            cur_i, cur_strophe = current
            can_replace = (
                cur_strophe.segments
                and isinstance(cur_strophe.segments[0], PlainSegment)
                and any(isinstance(seg, ChordedSegment) for seg in cur_strophe.segments)
                and prev_strophe.segments
                and isinstance(prev_strophe.segments[-1], ChordedSegment)
            )
            if can_replace:
                replacements.append(
                    (cur_i, ChordedSegment(chord=prev_strophe.segments[-1].chord, text=cur_strophe.segments[0].text))
                )
        for item_i, repl in replacements:
            items[item_i].segments[0] = repl
        return items

    @staticmethod
    def _recognize_codas(items: list[Strophe | Annotation]) -> list[Strophe | Annotation]:
        marks = [(i, item.mark) for i, item in enumerate(items) if isinstance(item, Strophe)]
        letter_counts = collections.Counter(mark.letter for i, mark in marks if isinstance(mark, LetteredStropheMark))
        if letter_counts == {"C": 1} and marks[-1][1] == LetteredStropheMark("C"):
            items[marks[-1][0]].mark = CodaMark()
            return items
        return items
