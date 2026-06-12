"""
Extension for collecting core stats like items scraped and start/finish times
"""

from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic
from typing import TYPE_CHECKING, Any

from scrapy import Spider, signals

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


class CoreStats:
    "A class to collect core statistics such as start time, finish time, and elapsed time."
    def __init__(self, stats: StatsCollector):
        self.stats: StatsCollector = stats
        self.start_time: datetime | None = None
        self._start_time_mono: float | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        "Create a CoreStats instance from the crawler and connect the necessary signals."
        assert crawler.stats
        o = cls(crawler.stats)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(o.item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(o.item_dropped, signal=signals.item_dropped)
        crawler.signals.connect(o.response_received, signal=signals.response_received)
        return o

    def spider_opened(self, spider: Spider) -> None:
        "Record the start time when the spider is opened."
        self.start_time = datetime.now(tz=timezone.utc)
        self._start_time_mono = monotonic()
        self.stats.set_value("start_time", self.start_time)

    def spider_closed(self, spider: Spider, reason: str) -> None:
        "Record the finish time and reason when the spider is closed."
        assert self.start_time is not None
        assert self._start_time_mono is not None
        finish_time, finish_time_mono = datetime.now(tz=timezone.utc), monotonic()
        elapsed_time_seconds = finish_time_mono - self._start_time_mono
        self.stats.set_value("elapsed_time_seconds", elapsed_time_seconds)
        self.stats.set_value("finish_time", finish_time)
        self.stats.set_value("finish_reason", reason)

    def item_scraped(self, item: Any, spider: Spider) -> None:
        "Increment the count of items scraped by the spider."
        self.stats.inc_value("item_scraped_count")

    def response_received(self, spider: Spider) -> None:
        "Increment the count of responses received by the spider."
        self.stats.inc_value("response_received_count")

    def item_dropped(self, item: Any, spider: Spider, exception: BaseException) -> None:
        "Record an item dropped by the spider and the associated exception."
        reason = exception.__class__.__name__
        self.stats.inc_value("item_dropped_count")
        self.stats.inc_value(f"item_dropped_reasons_count/{reason}")
