import collections
import dataclasses
import locale
import logging
from typing import ClassVar

from pysongbook.model import Annotation, AuthorAnnotation, Song, TitleAnnotation


@dataclasses.dataclass(frozen=True)
class IndexItem:
    label: str
    order: int
    song: Song
    specifier: str | None = None


@dataclasses.dataclass(frozen=True)
class SongIndex:
    title: str
    groups: dict[str, list[IndexItem]]
    is_initial: bool = False


@dataclasses.dataclass(frozen=True)
class IndexBuilder:
    title: str
    group_annotation_type: type[Annotation]
    label_annotation_type: type[Annotation] = TitleAnnotation
    specifier_annotation_type: type[Annotation] | None = None
    is_initial: ClassVar[bool] = False

    def group(self, label: str) -> str:
        return label

    def build(self, songs: list[Song]) -> SongIndex:
        items = [
            IndexItem(label=label, order=i + 1, song=song, specifier=None)
            for i, song in enumerate(songs)
            if (label := self._get_annotation(song, self.label_annotation_type)) is not None
        ]
        if self.specifier_annotation_type:
            items = self._add_specifiers(items)
        groups = collections.defaultdict(list)
        for item in items:
            group_annot = self._get_annotation(item.song, self.group_annotation_type)
            if group_annot is not None:
                group = self.group(group_annot)
                groups[group].append(item)
        return SongIndex(
            groups=dict(sorted(groups.items(), key=(lambda tup: locale.strxfrm(tup[0])))),
            is_initial=self.is_initial,
            title=self.title,
        )

    def _add_specifiers(self, items: list[IndexItem]) -> list[IndexItem]:
        label_counts = collections.Counter(item.label for item in items)
        duplicate_labels = {label for label, count in label_counts.items() if count > 1}
        return [
            dataclasses.replace(item, specifier=specifier)
            if item.label in duplicate_labels and (specifier := self._get_specifier_annotation(item.song)) is not None
            else item
            for item in items
        ]

    @staticmethod
    def _get_annotation(song: Song, annotation_type: type[Annotation]) -> str | None:
        annots = song.get_annotations_of_type(annotation_type)
        if len(annots) != 1:
            logging.warning("expected exactly one %s annotation, got %d", annotation_type.__name__, len(annots))
            if not annots:
                return None
        return annots[0].string

    def _get_specifier_annotation(self, song: Song) -> str | None:
        return self._get_annotation(song, self.specifier_annotation_type) if self.specifier_annotation_type else None

    def sort_key(self, song: Song) -> tuple[str | None, ...]:
        return (
            locale.strxfrm(self._get_annotation(song, self.label_annotation_type) or ""),
            locale.strxfrm(self._get_specifier_annotation(song) or ""),
        )


class InitialIndexBuilder(IndexBuilder):
    NUMERIC_LABEL = "0-9"
    is_initial: ClassVar[bool] = True

    def group(self, label: str) -> str:
        if not label:
            raise ValueError
        if label[0].isdigit():
            return self.NUMERIC_LABEL
        lup = label.upper()
        if lup.startswith("CH"):  # TODO internationalize this
            return "Ch"
        return label[0]


class MappedIndexBuilder(IndexBuilder):
    mapping: dict[str, str] = dataclasses.field(default_factory=dict)

    def group(self, label: str) -> str:
        return self.mapping.get(label, label)


INDEX_BUILDERS = {
    # TODO internationalize this
    "titleidx": InitialIndexBuilder(
        group_annotation_type=TitleAnnotation, specifier_annotation_type=AuthorAnnotation, title="Písně podle názvu"
    ),
    "authidx": IndexBuilder(group_annotation_type=AuthorAnnotation, title="Písně podle autora"),
    # "Písně podle jazyka": MappedIndexBuilder(annotation_type=LanguageAnnotation),
    # "Písně podle žánru": MappedIndexBuilder(annotation_type=GenreAnnotation),
}
PRIMARY_INDEX_BUILDER = INDEX_BUILDERS["titleidx"]


def build_indices(songs: list[Song]) -> dict[str, SongIndex]:
    return {name: builder.build(songs) for name, builder in INDEX_BUILDERS.items()}
