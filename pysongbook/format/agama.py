import re

from pysongbook.format.bracket import BracketFormat
from pysongbook.model import ChordedSegment, Song, Strophe, StropheSegment


class AgamaFormat(BracketFormat):
    name: str = "agama"
    other_names = ("twoline", "ultimate-guitar")
    empty_line_pattern: re.Pattern[str] = re.compile(r"\n\s*\n")
    empty_startline_pattern: re.Pattern[str] = re.compile(r"^\s*\n")

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
