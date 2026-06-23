"""Base types shared by all document parsers."""

from dataclasses import dataclass, field


@dataclass
class ParsedPage:
    page_number: int
    text: str
    tables: list[str] = field(default_factory=list)   # Markdown-formatted tables
    figures: list[str] = field(default_factory=list)  # LLM-generated figure descriptions
    section_heading: str | None = None


@dataclass
class ParsedDocument:
    pages: list[ParsedPage]
    title: str | None = None
    language: str | None = None
    warnings: list[str] = field(default_factory=list)  # partial parse issues
