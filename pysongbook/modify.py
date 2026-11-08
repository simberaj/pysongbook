import abc
from collections import Counter
import copy
import dataclasses
import itertools
from typing import cast

from pysongbook.model import (
    Annotation,
    BaseStropheSegmentCollection,
    ChordedSegment,
    ChordlessSegment,
    ChorusMark,
    CodaMark,
    LetteredStropheMark,
    ModifiedStropheRepeat,
    NumberedStropheMark,
    RepeatStropheWithSameMark,
    SimpleStropheRepeat,
    Song,
    Strophe,
    StropheSegment,
    UnknownChordSegment,
)


class SongModifier(abc.ABC):
    @abc.abstractmethod
    def modify(self, song: Song) -> Song:
        raise NotImplementedError


class SongItemModifier(SongModifier, abc.ABC):
    def modify(self, song: Song) -> Song:
        return Song(items=self.modify_items(song.items), annotations=song.annotations)

    @abc.abstractmethod
    def modify_items(self, items: list[Strophe | Annotation]) -> list[Strophe | Annotation]:
        raise NotImplementedError


class LinkStropheRepeats(SongItemModifier):
    def modify_items(self, items: list[Strophe | Annotation]) -> list[Strophe | Annotation]:
        linked_items = []
        for i, item in enumerate(items):
            if isinstance(item, RepeatStropheWithSameMark):
                # Find the strophe to repeat.
                for link_item in reversed(list(items[:i])):
                    if (
                        isinstance(link_item, Strophe)
                        and not isinstance(link_item, RepeatStropheWithSameMark)
                        and link_item.mark == item.mark
                    ):
                        break
                else:
                    raise ValueError(f"cannot find strophe of mark {item.mark} to repeat")
                if item.segments:
                    # This is a repeat of the strophe, but modified. Inferring the exact form of the strophe is not
                    # meaningfully possible, except for the reader. Preserving the info.
                    # for seg in item.segments:
                    #     if isinstance(seg, StropheSegment):
                    #         first_segment_text = seg.text
                    #         break
                    # else:
                    #     first_segment_text = str(uuid.uuid4())  # something that will never appear
                    # for i, lseg in enumerate(link_item.segments):
                    #     if isinstance(lseg, StropheSegment) and first_segment_text in lseg.text:
                    #         break
                    # break_segment = dataclasses.replace(lseg, text=lseg.text[: lseg.text.find(first_segment_text)])
                    # result_segments = [
                    #     RepeatedStrophePart(link_item.segments[:i] + [break_segment])
                    # ] + cls._ffill_chord(item.segments, break_segment)
                    # this is _ffill_chord():
                    #     if not hasattr(source_segment, "chord"):
                    #         return segments
                    #     out_segments = []
                    #     for seg in segments:
                    #         if hasattr(seg, "chord"):
                    #             break
                    #         elif isinstance(seg, StropheSegment):
                    #             out_segments.append(ChordedSegment(chord=source_segment.chord, text=seg.text))
                    #         else:
                    #             out_segments.append(seg)
                    #     return out_segments + segments[len(out_segments) :]
                    result_item = ModifiedStropheRepeat(repeated_strophe=link_item, segments=item.segments)
                else:
                    result_item = SimpleStropheRepeat(repeated_strophe=link_item)
                linked_items.append(result_item)
            else:
                linked_items.append(item)
        return linked_items


class InferChorusRepetition(SongItemModifier):
    def modify_items(self, items: list[Strophe | Annotation]) -> list[Strophe | Annotation]:
        strophe_types = [type(item.mark) for item in items if isinstance(item, Strophe)]
        if len(strophe_types) <= 2 or len(strophe_types) < len(items):
            return items
        type_pattern = [NumberedStropheMark, ChorusMark] + [NumberedStropheMark] * (len(strophe_types) - 2)
        if strophe_types == type_pattern:
            # Inlay chorus repetition after the second and each subsequent strophe.
            repeat_chorus = SimpleStropheRepeat(cast(Strophe, items[1]))
            inlaid = items[:2] + [item for strophe in items[2:] for item in (strophe, repeat_chorus)]
            return inlaid
        return items


class FillInitialUnknownChordSegments(SongItemModifier):
    def modify_items(self, items: list[Strophe | Annotation]) -> list[Strophe | Annotation]:
        replacements = []
        strophes: list[tuple[int, Strophe]] = [(i, item) for i, item in enumerate(items) if isinstance(item, Strophe)]
        for prev, current in itertools.pairwise(strophes):
            prev_i, prev_strophe = prev
            cur_i, cur_strophe = current
            can_replace = (
                cur_strophe.segments
                and not isinstance(cur_strophe, SimpleStropheRepeat)
                and isinstance(cur_strophe.segments[0], UnknownChordSegment)
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


class RecognizeCodas(SongItemModifier):
    def modify_items(self, items: list[Strophe | Annotation]) -> list[Strophe | Annotation]:
        marks = [(i, item.mark) for i, item in enumerate(items) if isinstance(item, Strophe)]
        letter_counts = Counter(mark.letter for i, mark in marks if isinstance(mark, LetteredStropheMark))
        if letter_counts == {"C": 1} and marks[-1][1] == LetteredStropheMark("C"):
            items[marks[-1][0]].mark = CodaMark()
            return items
        return items


class StripStropheWhitespace(SongItemModifier):
    def modify_items(self, items: list[Strophe | Annotation]) -> list[Strophe | Annotation]:
        out_items = []
        for item in items:
            if isinstance(item, Strophe):
                strophe = copy.deepcopy(item)
                self._lstrip(strophe.segments)
                self._rstrip(strophe.segments)
                out_items.append(strophe)
            else:
                out_items.append(item)
        return out_items

    def _lstrip(self, segments: list[StropheSegment]) -> None:
        if not segments:
            return
        first_seg = segments[0]
        if isinstance(first_seg, ChordedSegment):
            return
        if isinstance(first_seg, ChordlessSegment):
            first_seg.text = first_seg.text.lstrip()
        elif isinstance(first_seg, BaseStropheSegmentCollection):
            self._lstrip(first_seg.segments)
        else:  # embedded annotations etc.
            self._lstrip(segments[1:])

    def _rstrip(self, segments: list[StropheSegment]) -> None:
        if not segments:
            return
        last_seg = segments[-1]
        if isinstance(last_seg, ChordedSegment | ChordlessSegment):
            last_seg.text = last_seg.text.rstrip()
        elif isinstance(last_seg, BaseStropheSegmentCollection):
            self._rstrip(last_seg.segments)
        else:
            self._rstrip(segments[:-1])


@dataclasses.dataclass(frozen=True)
class CompositeModifier(SongModifier):
    modifiers: list[SongModifier]

    def modify(self, song: Song) -> Song:
        for modifier in self.modifiers:
            song = modifier.modify(song)
        return song


NORMALIZER = CompositeModifier(
    modifiers=[
        LinkStropheRepeats(),
        InferChorusRepetition(),
        FillInitialUnknownChordSegments(),
        RecognizeCodas(),
        StripStropheWhitespace(),
    ]
)
