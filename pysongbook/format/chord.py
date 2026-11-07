import abc
from collections.abc import Generator
import dataclasses
import logging
import re
from typing import cast

from pysongbook.format.core import SongParseError
from pysongbook.model import (
    NOTES,
    AddedNote,
    Altered,
    BassNote,
    Chord,
    ChordModifier,
    DominantSeventh,
    GenericChordModifier,
    HigherNote,
    MajorSeventh,
    Minor,
    Note,
    Suspended,
)


DEFAULT_TONE_PATTERN_STR: str = r"[A-H](?:#|b)?"


class ChordParser(abc.ABC):
    @abc.abstractmethod
    def parse(self, chord_str: str) -> Chord:
        raise NotImplementedError


@dataclasses.dataclass
class SimpleTextChordModifierParseRule:
    pattern: re.Pattern[str]
    result_type: type[ChordModifier]


class DynamicTextChordModifierParseRule(abc.ABC):
    pattern: re.Pattern[str]

    @abc.abstractmethod
    def parse(self, match: re.Match) -> ChordModifier:
        raise NotImplementedError


class HigherNoteParseRule(DynamicTextChordModifierParseRule):
    pattern: re.Pattern[str] = re.compile("|".join(str(x) for x in HigherNote.allowed_factors))

    def parse(self, match: re.Match) -> HigherNote:
        return HigherNote(int(match.group()))


class AddedNoteParseRule(DynamicTextChordModifierParseRule):
    pattern: re.Pattern[str] = re.compile(r"(?:\+|add)(\d+)")

    def parse(self, match: re.Match) -> AddedNote:
        return AddedNote(int(match.group(1)))


class SuspendedParseRule(DynamicTextChordModifierParseRule):
    pattern: re.Pattern[str] = re.compile(r"sus(\d+)")

    def parse(self, match: re.Match) -> Suspended:
        return Suspended(int(match.group(1)))


class AlteredParseRule(DynamicTextChordModifierParseRule):
    pattern: re.Pattern[str] = re.compile(r"(\+|dim|b)(\d*)")

    def parse(self, match: re.Match) -> Altered:
        return Altered(direction=match.group(1), factor=(5 if not match.group(2) else int(match.group(2))))


class BassNoteParseRule(DynamicTextChordModifierParseRule):
    pattern: re.Pattern[str] = re.compile(r"/" + DEFAULT_TONE_PATTERN_STR)

    def parse(self, match: re.Match) -> BassNote:
        bass_tone = match.group()[1:]
        if bass_tone not in NOTES:
            raise SongParseError(f"invalid bass note: {bass_tone}")
        return BassNote(cast(Note, bass_tone))


@dataclasses.dataclass
class TextChordParser:
    tone_pattern: re.Pattern[str] = re.compile(DEFAULT_TONE_PATTERN_STR)
    modifier_parse_rules: tuple[SimpleTextChordModifierParseRule | DynamicTextChordModifierParseRule, ...] = (
        SimpleTextChordModifierParseRule(re.compile(r"maj7?"), MajorSeventh),
        SimpleTextChordModifierParseRule(re.compile(r"m"), Minor),
        SimpleTextChordModifierParseRule(re.compile(r"7"), DominantSeventh),
        HigherNoteParseRule(),
        AddedNoteParseRule(),
        SuspendedParseRule(),
        AlteredParseRule(),
        BassNoteParseRule(),
    )

    def parse(self, chord_str: str) -> Chord:
        if not chord_str:
            raise SongParseError("empty chord")
        root = self.tone_pattern.match(chord_str)
        if root is None or root.group() not in NOTES:
            raise SongParseError(f"invalid chord major: {chord_str}")
        modifiers = list(self.parse_modifiers(chord_str[root.end() :]))
        for modif in modifiers:
            if isinstance(modif, GenericChordModifier):
                logging.warning(f"unknown chord modifier: {modif.string} in chord {chord_str}")
        return Chord(cast(Note, root.group()), modifiers=modifiers)

    def parse_modifiers(self, modif_str: str) -> Generator[ChordModifier, None, None]:
        while modif_str:
            for rule in self.modifier_parse_rules:
                match = rule.pattern.match(modif_str)
                if match is not None:
                    yield (
                        rule.result_type() if isinstance(rule, SimpleTextChordModifierParseRule) else rule.parse(match)
                    )
                    modif_str = modif_str[len(match.group()) :]
                    break
            else:
                yield GenericChordModifier(modif_str)
                return
