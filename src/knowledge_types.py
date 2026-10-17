from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class KnowledgeError(ValueError):
    """Invalid input or unavailable documentary knowledge."""


class DocumentKind(str, Enum):
    REFERENCE = "reference"
    PROPOSAL = "proposal"
    HISTORICAL_EVIDENCE = "historical_evidence"


class Verification(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class Document:
    path: str
    component: str
    kind: DocumentKind
    verification: Verification
    document_date: str | None
    last_verified: str | None


@dataclass(frozen=True)
class Section:
    title: str
    heading: str
    start_line: int
    end_line: int
    content: str


@dataclass(frozen=True)
class Source:
    document: Document
    fingerprint: str
    sections: tuple[Section, ...]


@dataclass(frozen=True)
class Corpus:
    workspace_root: str
    catalog_path: str
    catalog_hash: str
    sources: tuple[Source, ...]


@dataclass(frozen=True)
class IndexReport:
    schema_version: int
    status: str
    added: int
    updated: int
    removed: int
    unchanged: int
    documents: int
    sections: int
    indexed_at: str
    elapsed_ms: float
    size_bytes: int


@dataclass(frozen=True)
class IndexStatus:
    schema_version: int
    status: str
    documents: int
    sections: int
    indexed_at: str | None
    issues: tuple[str, ...]
    size_bytes: int


@dataclass(frozen=True)
class SearchHit:
    path: str
    component: str
    kind: str
    verification: str
    document_date: str | None
    last_verified: str | None
    title: str
    heading: str
    start_line: int
    end_line: int
    content: str
