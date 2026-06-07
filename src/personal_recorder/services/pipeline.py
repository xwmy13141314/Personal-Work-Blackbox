from __future__ import annotations

from personal_recorder.models.types import Event
from personal_recorder.processors.extractor import InsightExtractor
from personal_recorder.processors.normalizer import EventNormalizer
from personal_recorder.processors.ranker import ImportanceRanker
from personal_recorder.repositories.event_repository import EventRepository


class ProcessingPipeline:
    def __init__(self, repository: EventRepository):
        self.repository = repository
        self.normalizer = EventNormalizer()
        self.ranker = ImportanceRanker()
        self.extractor = InsightExtractor()

    def ingest(self, raw_event: dict) -> Event:
        event = self.normalizer.normalize(raw_event)
        event.importance_score = self.ranker.score(event)
        self.repository.add_event(event)
        self.repository.add_important_items(self.extractor.extract_important_items(event))
        self.repository.add_action_items(self.extractor.extract_action_items(event))
        return event
