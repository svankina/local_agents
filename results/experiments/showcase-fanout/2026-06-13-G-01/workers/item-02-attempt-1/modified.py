"""
Scrapy extension for collecting scraping stats
"""

from __future__ import annotations

import logging
import pprint
from typing import TYPE_CHECKING, Any

from scrapy.utils.decorators import _warn_spider_arg

if TYPE_CHECKING:
    from scrapy import Spider
    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)


StatsT = dict[str, Any]


class StatsCollector:
    "A base class for collecting and managing spider statistics."
    def __init__(self, crawler: Crawler):
        self._dump: bool = crawler.settings.getbool("STATS_DUMP")
        self._stats: StatsT = {}
        self._crawler: Crawler = crawler

    def __getattribute__(self, name: str) -> Any:
        cached_name = f"_cached_{name}"
        try:
            return super().__getattribute__(cached_name)
        except AttributeError:
            pass

        original_attr = super().__getattribute__(name)

        if name in {
            "get_value",
            "get_stats",
            "set_value",
            "set_stats",
            "inc_value",
            "max_value",
            "min_value",
            "clear_stats",
            "open_spider",
            "close_spider",
        } and callable(original_attr):
            wrapped = _warn_spider_arg(original_attr)
            setattr(self, cached_name, wrapped)
            return wrapped

        return original_attr

    def get_value(
        self, key: str, default: Any = None, spider: Spider | None = None
    ) -> Any:
        "Retrieve the value for a specific key, returning default if missing, for the spider."
        return self._stats.get(key, default)

    def get_stats(self, spider: Spider | None = None) -> StatsT:
        "Return the current dictionary of statistics for the spider."
        return self._stats

    def set_value(self, key: str, value: Any, spider: Spider | None = None) -> None:
        "Set the value for a specific key for the spider."
        self._stats[key] = value

    def set_stats(self, stats: StatsT, spider: Spider | None = None) -> None:
        "Set the statistics for the spider to a new stats dictionary."
        self._stats = stats

    def inc_value(
        self, key: str, count: int = 1, start: int = 0, spider: Spider | None = None
    ) -> None:
        "Increment the value of a key by count, starting from start, for the spider."
        d = self._stats
        d[key] = d.setdefault(key, start) + count

    def max_value(self, key: str, value: Any, spider: Spider | None = None) -> None:
        "Update the maximum value for a key with the new value for the spider."
        self._stats[key] = max(self._stats.setdefault(key, value), value)

    def min_value(self, key: str, value: Any, spider: Spider | None = None) -> None:
        "Update the minimum value for a key with the new value for the spider."
        self._stats[key] = min(self._stats.setdefault(key, value), value)

    def clear_stats(self, spider: Spider | None = None) -> None:
        "Clear all collected statistics for the given spider."
        self._stats.clear()

    def open_spider(self, spider: Spider | None = None) -> None:
        "Initialize the statistics collection for the spider."
        pass

    def close_spider(
        self, spider: Spider | None = None, reason: str | None = None
    ) -> None:
        "Finalize and dump the statistics for the spider, optionally providing a reason."
        if self._dump:
            logger.info(
                "Dumping Scrapy stats:\n" + pprint.pformat(self._stats),
                extra={"spider": self._crawler.spider},
            )
        self._persist_stats(self._stats)

    def _persist_stats(self, stats: StatsT) -> None:
        pass


class MemoryStatsCollector(StatsCollector):
    "A stats collector that persists statistics in memory for each spider."
    def __init__(self, crawler: Crawler):
        super().__init__(crawler)
        self.spider_stats: dict[str, StatsT] = {}

    def _persist_stats(self, stats: StatsT) -> None:
        if self._crawler.spider:
            self.spider_stats[self._crawler.spider.name] = stats


class DummyStatsCollector(StatsCollector):
    "A dummy implementation of StatsCollector that does not persist any data."
    def get_value(
        self, key: str, default: Any = None, spider: Spider | None = None
    ) -> Any:
        "Retrieve a value for a given key from the dummy collector, returning default if not found, for a spider."
        return default

    def set_value(self, key: str, value: Any, spider: Spider | None = None) -> None:
        "Set a specific value for a key in the dummy collector for a spider."
        pass

    def set_stats(self, stats: StatsT, spider: Spider | None = None) -> None:
        "Replace the current stats with a new stats dictionary for the spider."
        pass

    def inc_value(
        self, key: str, count: int = 1, start: int = 0, spider: Spider | None = None
    ) -> None:
        "Increment a value for a key by a count starting from start for a specific spider."
        pass

    def max_value(self, key: str, value: Any, spider: Spider | None = None) -> None:
        "Update the maximum value for a key based on the provided value for a spider."
        pass

    def min_value(self, key: str, value: Any, spider: Spider | None = None) -> None:
        "Update the minimum value for a key based on the provided value for a spider."
        pass
