"""Compatibility exports for the preserved v4 dashboard.

Legacy calls use retrieved excerpts. Production supplies a shared local provider;
importing this module never loads a model or performs network requests.
"""
from nexus.research import build_search_query, get_page_text, is_public_https, research_web

__all__ = ["build_search_query", "get_page_text", "is_public_https", "research_web"]
