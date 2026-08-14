"""Single source of truth for RSSFeed.source_format -> adapter class dispatch.

Previously duplicated identically in collection_tasks.py and
document_processor.py; aggregation_tasks.py::_stage_collect never used it at
all and hardcoded GoogleNewsRSSAdapter (see FINDINGS.md D3). All three call
sites now import from here so the mapping can't drift out of sync again.
"""
from app.adapters.rss import RSSAdapter
from app.adapters.gdelt import GDELTAdapter
from app.adapters.hn_algolia import HNAlgoliaAdapter

ADAPTER_REGISTRY = {
    "rss": RSSAdapter,
    "gdelt_json": GDELTAdapter,
    "hn_algolia_json": HNAlgoliaAdapter,
}
