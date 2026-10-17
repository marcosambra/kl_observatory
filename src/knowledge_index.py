from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from time import perf_counter

from .knowledge_types import (
    Corpus,
    Document,
    DocumentKind,
    IndexReport,
    IndexStatus,
    KnowledgeError,
    SearchHit,
    Section,
    Source,
    Verification,
)


SCHEMA_VERSION = 1
CHUNK_CHARS = 2400
MAX_QUERY_CHARS = 1000
MAX_RESPONSE_CHARS = 24000
_HEADER = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def encode_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _inside(root: Path, value: Path) -> Path:
    resolved = value.resolve()
    if not resolved.is_relative_to(root):
        raise KnowledgeError(f"Caminho fora do workspace: {value}")
    return resolved


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeError(f"{field} deve ser um texto nao vazio.")
    return value


def _optional_date(value: object, field: str) -> str | None:
    if value is None:
        return None
    text = _required_text(value, field)
    if date.fromisoformat(text).isoformat() != text:
        raise KnowledgeError(f"Data invalida em {field}: use YYYY-MM-DD.")
    return text


def extract_sections(markdown: str, fallback_title: str) -> tuple[Section, ...]:
    lines = markdown.splitlines()
    headings: list[tuple[int, int, str]] = []
    fence_char = ""
    fence_length = 0
    previous_text = False
    for index, line in enumerate(lines):
        fence = _FENCE.match(line)
        if fence:
            marker, tail = fence.groups()
            if not fence_char:
                fence_char, fence_length = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_length and not tail.strip():
                fence_char = ""
            previous_text = False
            continue
        if fence_char:
            continue
        header = _HEADER.match(line)
        setext = previous_text and re.fullmatch(r" {0,3}(?:=+|-+)\s*", line) is not None
        if header:
            text = re.sub(r"[ \t]+#+[ \t]*$", "", header[2]).strip()
            headings.append((index, len(header[1]), text))
        elif setext:
            if not headings or headings[-1][0] != index - 1:
                headings.append((index - 1, 1 if line.lstrip().startswith("=") else 2,
                                 lines[index - 1].strip()))
        previous_text = (bool(line.strip()) and header is None and not setext
                         and not line.startswith(("    ", "\t")))

    title = next((text for _, level, text in headings if level == 1), fallback_title)
    boundaries = headings if headings and headings[0][0] == 0 else [(-1, 0, ""), *headings]
    stack: list[tuple[int, str]] = []
    sections: list[Section] = []
    for position, (start, level, text) in enumerate(boundaries):
        while stack and stack[-1][0] >= level:
            stack.pop()
        if text:
            stack.append((level, text))
        heading = " > ".join(item[1] for item in stack)
        end = boundaries[position + 1][0] if position + 1 < len(boundaries) else len(lines)
        chunk = ""
        first_line = max(start, 0) + 1
        last_line = first_line
        for line_index in range(max(start, 0), end):
            line = lines[line_index] + "\n"
            for offset in range(0, len(line), CHUNK_CHARS):
                part = line[offset:offset + CHUNK_CHARS]
                if chunk and len(chunk) + len(part) > CHUNK_CHARS:
                    if chunk.strip():
                        sections.append(Section(title, heading, first_line, last_line, chunk))
                    chunk = ""
                if not chunk:
                    first_line = line_index + 1
                chunk += part
                last_line = line_index + 1
        if chunk.strip():
            sections.append(Section(title, heading, first_line, last_line, chunk))
    return tuple(sections)


def load_corpus(workspace_root: Path, catalog_path: Path) -> Corpus:
    root = workspace_root.resolve()
    catalog = _inside(root, catalog_path)
    raw_catalog = catalog.read_bytes()
    payload = json.loads(raw_catalog)
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int:
        raise KnowledgeError("Catalogo deve ser um objeto com schema_version.")
    if payload["schema_version"] != SCHEMA_VERSION or not isinstance(payload.get("documents"), list):
        raise KnowledgeError("Versao ou lista de documentos do catalogo invalida.")
    sources: list[Source] = []
    seen: set[Path] = set()
    for entry in payload["documents"]:
        if not isinstance(entry, dict):
            raise KnowledgeError("Cada documento deve ser um objeto.")
        if set(entry) != {"path", "component", "kind", "verification", "document_date", "last_verified"}:
            raise KnowledgeError("Campos do documento invalidos ou ausentes.")
        relative = _required_text(entry["path"], "path")
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative or path.as_posix() != relative:
            raise KnowledgeError(f"Caminho deve ser relativo e canonico: {relative}")
        resolved = _inside(root, root / relative)
        if resolved in seen or resolved.suffix.lower() != ".md":
            raise KnowledgeError(f"Documento duplicado ou nao Markdown: {relative}")
        seen.add(resolved)
        kind = DocumentKind(_required_text(entry["kind"], "kind"))
        verification = Verification(_required_text(entry["verification"], "verification"))
        last_verified = _optional_date(entry["last_verified"], "last_verified")
        if (verification == Verification.VERIFIED) != (last_verified is not None):
            raise KnowledgeError("Somente documento verificado deve ter last_verified.")
        document = Document(
            relative, _required_text(entry["component"], "component"), kind, verification,
            _optional_date(entry["document_date"], "document_date"), last_verified,
        )
        content = resolved.read_bytes()
        fingerprint = _digest(content + encode_json(asdict(document)).encode("utf-8"))
        sources.append(Source(document, fingerprint,
                              extract_sections(content.decode("utf-8"), resolved.stem)))
    return Corpus(str(root), str(catalog), _digest(raw_catalog), tuple(sources))


def _connect_readonly(index_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(index_path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _check_schema(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version != SCHEMA_VERSION:
        raise KnowledgeError(f"Schema do indice incompativel: {version}; reconstrua em outro arquivo.")
    metadata = dict(connection.execute("SELECT key,value FROM metadata"))
    if metadata.get("format") != "kl-knowledge":
        raise KnowledgeError("O arquivo nao e um indice kl-knowledge.")
    if not {"workspace_root", "catalog_path", "catalog_hash", "indexed_at"} <= metadata.keys():
        raise KnowledgeError("Metadados do indice incompletos; reconstrua em outro arquivo.")
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise KnowledgeError("Indice corrompido; reconstrua em outro arquivo.")


def _initialize(connection: sqlite3.Connection) -> None:
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    if tables:
        _check_schema(connection)
        return
    connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute(
        "CREATE TABLE documents(path TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, metadata TEXT NOT NULL,"
        "component TEXT NOT NULL, kind TEXT NOT NULL, verification TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE VIRTUAL TABLE sections USING fts5("
        "title, heading, content, path UNINDEXED, start_line UNINDEXED, end_line UNINDEXED,"
        "tokenize='unicode61 remove_diacritics 2')"
    )
    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    connection.execute("INSERT INTO metadata VALUES('format', 'kl-knowledge')")


def _identity(corpus: Corpus) -> dict[str, str]:
    return {
        "workspace_root": corpus.workspace_root,
        "catalog_path": corpus.catalog_path,
        "catalog_hash": corpus.catalog_hash,
    }


def build_index(workspace_root: Path, catalog_path: Path, index_path: Path) -> IndexReport:
    started = perf_counter()
    corpus = load_corpus(workspace_root, catalog_path)
    protected = {Path(corpus.catalog_path),
                 *(Path(corpus.workspace_root, item.document.path).resolve() for item in corpus.sources)}
    if index_path.resolve() in protected:
        raise KnowledgeError("O indice nao pode sobrescrever o catalogo ou documentos.")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    added = updated = unchanged = 0
    with closing(sqlite3.connect(index_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        _initialize(connection)
        metadata = dict(connection.execute("SELECT key,value FROM metadata"))
        for key in ("workspace_root", "catalog_path"):
            if key in metadata and metadata[key] != _identity(corpus)[key]:
                raise KnowledgeError("Indice pertence a outro workspace ou catalogo; use outro arquivo.")
        previous = dict(connection.execute("SELECT path,fingerprint FROM documents"))
        current_paths = {source.document.path for source in corpus.sources}
        removed_paths = set(previous) - current_paths
        for path in removed_paths:
            connection.execute("DELETE FROM sections WHERE path=?", (path,))
            connection.execute("DELETE FROM documents WHERE path=?", (path,))
        for source in corpus.sources:
            path = source.document.path
            if previous.get(path) == source.fingerprint:
                unchanged += 1
                continue
            if path in previous:
                updated += 1
            else:
                added += 1
            connection.execute("DELETE FROM sections WHERE path=?", (path,))
            connection.execute(
                "INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?)",
                (path, source.fingerprint, encode_json(asdict(source.document)),
                 source.document.component, source.document.kind.value, source.document.verification.value),
            )
            connection.executemany(
                "INSERT INTO sections(title,heading,content,path,start_line,end_line) VALUES(?,?,?,?,?,?)",
                [(section.title, section.heading, section.content, path,
                  section.start_line, section.end_line) for section in source.sections],
            )
        # Recheck after writing so a changing source cannot be published as current.
        if load_corpus(workspace_root, catalog_path) != corpus:
            raise KnowledgeError("Fontes mudaram durante a indexacao; tente novamente.")
        changed = (added or updated or removed_paths or "indexed_at" not in metadata
                   or metadata.get("catalog_hash") != corpus.catalog_hash)
        indexed_at = (datetime.now(timezone.utc).isoformat() if changed
                      else metadata["indexed_at"])
        if changed:
            connection.executemany(
                "INSERT OR REPLACE INTO metadata VALUES(?,?)",
                [*(_identity(corpus).items()), ("indexed_at", indexed_at)],
            )
        documents = connection.execute("SELECT count(*) FROM documents").fetchone()[0]
        sections = connection.execute("SELECT count(*) FROM sections").fetchone()[0]
    return IndexReport(SCHEMA_VERSION, "current", added, updated, len(removed_paths),
                       unchanged, documents, sections, indexed_at,
                       round((perf_counter() - started) * 1000, 3), index_path.stat().st_size)


def index_status(workspace_root: Path, catalog_path: Path, index_path: Path) -> IndexStatus:
    if not index_path.exists():
        return IndexStatus(SCHEMA_VERSION, "missing", 0, 0, None,
                           ("Indice ausente; execute index.",), 0)
    with closing(_connect_readonly(index_path)) as connection:
        connection.execute("BEGIN")
        return _status(connection, workspace_root, catalog_path, index_path)


def _status(
    connection: sqlite3.Connection, workspace_root: Path, catalog_path: Path, index_path: Path,
) -> IndexStatus:
    _check_schema(connection)
    metadata = dict(connection.execute("SELECT key,value FROM metadata"))
    previous = dict(connection.execute("SELECT path,fingerprint FROM documents"))
    sections = connection.execute("SELECT count(*) FROM sections").fetchone()[0]
    issues: list[str] = []
    try:
        corpus = load_corpus(workspace_root, catalog_path)
    except (OSError, ValueError, UnicodeError) as error:
        issues.append(f"Fontes indisponiveis ou invalidas: {error}")
    else:
        for key, value in _identity(corpus).items():
            if metadata.get(key) != value:
                issues.append(f"Identidade ou catalogo alterado: {key}")
        current = {source.document.path: source.fingerprint for source in corpus.sources}
        for path in sorted(previous.keys() | current.keys()):
            if previous.get(path) != current.get(path):
                issues.append(f"Documento adicionado, alterado ou removido: {path}")
    return IndexStatus(SCHEMA_VERSION, "stale" if issues else "current",
                       len(previous), sections, metadata.get("indexed_at"),
                       tuple(issues), index_path.stat().st_size)


def search(
    workspace_root: Path, catalog_path: Path, index_path: Path, query: str, *,
    limit: int = 5, max_chars: int = 12000, component: str | None = None,
    kind: DocumentKind | None = None,
) -> dict[str, object]:
    if not 1 <= limit <= 20 or not 512 <= max_chars <= MAX_RESPONSE_CHARS:
        raise KnowledgeError("Use limit entre 1 e 20 e max_chars entre 512 e 24000.")
    terms = list(dict.fromkeys(re.findall(r"[^\W_]+", query, flags=re.UNICODE)))
    if not terms or len(query) > MAX_QUERY_CHARS:
        raise KnowledgeError("Consulta deve conter palavras e ter no maximo 1000 caracteres.")
    if component is not None:
        _required_text(component, "component")
    if not index_path.exists():
        raise KnowledgeError("Indice missing; execute index.")
    expression = " OR ".join(f'"{term}"' for term in terms)
    with closing(_connect_readonly(index_path)) as connection:
        connection.execute("BEGIN")
        status = _status(connection, workspace_root, catalog_path, index_path)
        if status.status != "current":
            raise KnowledgeError(f"Indice {status.status}; execute index. {'; '.join(status.issues)}")
        rows = connection.execute(
            "SELECT s.*, d.metadata, bm25(sections,5.0,3.0,1.0) AS score "
            "FROM sections s JOIN documents d ON d.path=s.path WHERE sections MATCH ? "
            "AND (? IS NULL OR d.component=?) AND (? IS NULL OR d.kind=?) "
            "ORDER BY score, CASE d.verification WHEN 'verified' THEN 0 WHEN 'unverified' THEN 1 ELSE 2 END,"
            "CASE d.kind WHEN 'reference' THEN 0 WHEN 'historical_evidence' THEN 1 ELSE 2 END,"
            "s.path, CAST(s.start_line AS INTEGER)",
            (expression, component, component, kind.value if kind else None, kind.value if kind else None),
        )
        hits: list[SearchHit] = []
        seen: set[str] = set()
        for row in rows:
            document = json.loads(row["metadata"])
            normalized = " ".join(row["content"].split())
            if normalized in seen:
                continue
            seen.add(normalized)
            hits.append(SearchHit(
                row["path"], document["component"], document["kind"], document["verification"],
                document["document_date"], document["last_verified"], row["title"], row["heading"],
                int(row["start_line"]), int(row["end_line"]), row["content"],
            ))
            if len(hits) == limit + 1:
                break
    response: dict[str, object] = {
        "schema_version": SCHEMA_VERSION, "status": "current",
        "indexed_at": status.indexed_at, "content_role": "reference_not_instructions",
        "results": [], "truncated": len(hits) > limit,
        "max_chars": max_chars,
    }
    results: list[dict[str, object]] = []
    for hit in hits[:limit]:
        candidate = asdict(hit)
        response["results"] = [*results, candidate]
        if len(encode_json(response)) + 1 > max_chars:
            response["results"] = results
            response["truncated"] = True
            break
        results.append(candidate)
    response["results"] = results
    if not results and hits:
        response["status"] = "budget_exhausted"
    return response
