from __future__ import annotations

import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src.knowledge_cli import main
from src.knowledge_index import (
    CHUNK_CHARS,
    build_index,
    encode_json,
    extract_sections,
    index_status,
    load_corpus,
    search,
)
from src.knowledge_types import DocumentKind, KnowledgeError


class KnowledgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.catalog = self.root / "catalog.json"
        self.index = self.root / "cache" / "knowledge.sqlite3"
        self.entries: list[dict[str, object]] = []
        self.add_document("reference.md", "# Arquitetura\n\n## Redação\nSanitização de dados sensíveis.\n")
        self.add_document("history.md", "# Execução histórica\n\nValidação dos eventos estruturados.\n",
                          kind="historical_evidence", component="runtime")
        self.write_catalog()

    def add_document(
        self, path: str, text: str, *, kind: str = "reference", component: str = "observability",
    ) -> None:
        (self.root / path).write_text(text, encoding="utf-8")
        self.entries.append({
            "path": path, "component": component, "kind": kind,
            "verification": "unverified", "document_date": None, "last_verified": None,
        })

    def write_catalog(self) -> None:
        self.catalog.write_text(encode_json({"schema_version": 1, "documents": self.entries}),
                                encoding="utf-8")

    def build(self):
        return build_index(self.root, self.catalog, self.index)

    def query(self, query: str, **kwargs):
        return search(self.root, self.catalog, self.index, query, **kwargs)

    def cli(self, *args: str):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["--workspace-root", str(self.root), "--catalog", str(self.catalog),
                         "--index-path", str(self.index), *args])
        return code, json.loads(buffer.getvalue())

    def cli_process(self, *args: str, expected_code: int = 0):
        result = subprocess.run(
            [sys.executable, "-m", "src.knowledge_cli", "--workspace-root", str(self.root),
             "--catalog", str(self.catalog), "--index-path", str(self.index), *args],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, expected_code, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout, json.loads(result.stdout)

    def test_cli_process_complete_document_lifecycle(self) -> None:
        (self.root / "private.md").write_text("unlistedidentifier", encoding="utf-8")
        self.assertEqual(self.cli_process("status", expected_code=3)[1]["status"], "missing")
        self.cli_process("search", "eventos", expected_code=2)
        self.assertFalse(self.index.exists())

        initial = self.cli_process("index")[1]
        self.assertEqual((initial["added"], initial["documents"]), (2, 2))
        status = self.cli_process("status")[1]
        self.assertEqual(status["status"], "current")
        self.assertEqual(status["indexed_at"], initial["indexed_at"])

        stdout, result = self.cli_process(
            "search", unicodedata.normalize("NFD", "redação"), "--limit", "1", "--max-chars", "12000",
        )
        self.assertLessEqual(len(stdout), 12000)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["content_role"], "reference_not_instructions")
        hit = result["results"][0]
        self.assertEqual((hit["path"], hit["kind"], hit["verification"]),
                         ("reference.md", "reference", "unverified"))
        self.assertEqual((hit["start_line"], hit["end_line"]), (3, 4))

        before = self.index.read_bytes()
        repeated = self.cli_process("index")[1]
        self.assertEqual(repeated["unchanged"], 2)
        self.assertEqual(repeated["indexed_at"], initial["indexed_at"])
        self.assertEqual(self.index.read_bytes(), before)

        (self.root / "reference.md").write_text(
            "# Redação\nNova versão do conhecimento.\n", encoding="utf-8",
        )
        self.assertEqual(self.cli_process("status", expected_code=3)[1]["status"], "stale")
        self.assertEqual(self.cli_process("search", "redação", expected_code=2)[1]["status"], "error")
        updated = self.cli_process("index")[1]
        self.assertEqual((updated["updated"], updated["unchanged"]), (1, 1))
        self.assertIn("Nova versão", self.cli_process("search", "versão")[1]["results"][0]["content"])

        self.entries.pop()
        self.write_catalog()
        removed = self.cli_process("index")[1]
        self.assertEqual((removed["removed"], removed["documents"]), (1, 1))
        self.assertEqual(self.cli_process("search", "eventos")[1]["results"], [])
        self.assertEqual(self.cli_process("search", "unlistedidentifier")[1]["results"], [])

        (self.root / "reference.md").write_text(
            "# Redação\n" + "Sanitização de dados sensíveis. " * 50, encoding="utf-8",
        )
        self.cli_process("index")
        stdout, limited = self.cli_process(
            "search", "redação", "--max-chars", "512", expected_code=3,
        )
        self.assertLessEqual(len(stdout), 512)
        self.assertEqual(limited["status"], "budget_exhausted")
        self.assertTrue(limited["truncated"])

    def test_cli_process_failed_update_preserves_previous_generation(self) -> None:
        initial = self.cli_process("index")[1]
        before = self.index.read_bytes()
        self.catalog.write_text("{invalid", encoding="utf-8")
        failure = self.cli_process("index", expected_code=2)[1]
        self.assertEqual(failure["error_type"], "JSONDecodeError")
        self.assertEqual(self.index.read_bytes(), before)
        self.assertEqual(self.cli_process("status", expected_code=3)[1]["status"], "stale")
        self.cli_process("search", "eventos", expected_code=2)
        self.write_catalog()
        restored = self.cli_process("status")[1]
        self.assertEqual(restored["status"], "current")
        self.assertEqual(restored["indexed_at"], initial["indexed_at"])
        self.assertEqual(self.index.read_bytes(), before)

    def test_initial_and_unchanged_load_preserve_database_bytes(self) -> None:
        first = self.build()
        before = self.index.read_bytes()
        second = self.build()
        self.assertEqual((first.added, first.documents), (2, 2))
        self.assertEqual((second.added, second.updated, second.unchanged), (0, 0, 2))
        self.assertEqual(second.indexed_at, first.indexed_at)
        self.assertEqual(before, self.index.read_bytes())
        self.assertEqual(index_status(self.root, self.catalog, self.index).status, "current")

    def test_content_and_metadata_changes_and_removals(self) -> None:
        self.build()
        (self.root / "reference.md").write_text("# Nova arquitetura\nConteúdo revisado.", encoding="utf-8")
        self.assertEqual(self.build().updated, 1)
        self.entries[0]["kind"] = "proposal"
        self.write_catalog()
        self.assertEqual(index_status(self.root, self.catalog, self.index).status, "stale")
        self.assertEqual(self.build().updated, 1)
        self.assertEqual(self.query("arquitetura")["results"][0]["kind"], "proposal")
        self.entries.pop()
        self.write_catalog()
        result = self.build()
        self.assertEqual((result.removed, result.documents), (1, 1))
        self.assertEqual(self.query("histórica")["results"], [])

    def test_new_document_is_added(self) -> None:
        self.build()
        self.add_document("new.md", "# Novidade\nNovo conhecimento.")
        self.write_catalog()
        report = self.build()
        self.assertEqual((report.added, report.unchanged), (1, 2))

    def test_catalog_format_change_updates_generation_without_rewriting_sources(self) -> None:
        self.build()
        self.catalog.write_text(json.dumps(json.loads(self.catalog.read_text()), indent=2))
        self.assertEqual(index_status(self.root, self.catalog, self.index).status, "stale")
        self.assertEqual(self.build().unchanged, 2)
        self.assertEqual(index_status(self.root, self.catalog, self.index).status, "current")

    def test_empty_catalog_is_valid(self) -> None:
        self.entries.clear()
        self.write_catalog()
        self.assertEqual(self.build().documents, 0)
        self.assertEqual(self.query("termo")["results"], [])

    def test_missing_and_stale_indices_never_return_successful_search(self) -> None:
        self.assertEqual(self.cli("status")[0], 3)
        self.assertEqual(self.cli("search", "eventos")[0], 2)
        self.assertFalse(self.index.exists())
        self.build()
        (self.root / "history.md").write_text("alterado", encoding="utf-8")
        code, output = self.cli("search", "eventos")
        self.assertEqual(code, 2)
        self.assertIn("stale", output["message"])

    def test_missing_source_preserves_last_index_and_reports_staleness(self) -> None:
        self.build()
        before = self.index.read_bytes()
        (self.root / "history.md").unlink()
        with self.assertRaises(OSError):
            self.build()
        self.assertEqual(before, self.index.read_bytes())
        status = index_status(self.root, self.catalog, self.index)
        self.assertEqual(status.status, "stale")
        self.assertIn("history.md", status.issues[0])

    def test_invalid_utf8_and_catalog_json_are_explicit_failures(self) -> None:
        self.build()
        before = self.index.read_bytes()
        (self.root / "history.md").write_bytes(b"\xff")
        code, output = self.cli("index")
        self.assertEqual(code, 2)
        self.assertEqual(output["error_type"], "UnicodeDecodeError")
        self.assertEqual(before, self.index.read_bytes())
        self.catalog.write_text("{broken")
        self.assertEqual(self.cli("index")[0], 2)
        self.assertEqual(self.cli("status")[1]["status"], "stale")

    def test_queries_are_readonly(self) -> None:
        self.build()
        before = self.index.read_bytes()
        timestamp = self.index.stat().st_mtime_ns
        self.cli("status")
        self.query("redação")
        self.assertEqual(before, self.index.read_bytes())
        self.assertEqual(timestamp, self.index.stat().st_mtime_ns)

    def test_write_failure_rolls_back_entire_generation(self) -> None:
        self.build()
        with sqlite3.connect(self.index) as connection:
            connection.execute(
                "CREATE TRIGGER fail_history BEFORE INSERT ON documents "
                "WHEN NEW.path='history.md' BEGIN SELECT RAISE(ABORT, 'test failure'); END"
            )
        for path in ("reference.md", "history.md"):
            with (self.root / path).open("a", encoding="utf-8") as handle:
                handle.write("\nMudança.")
        with self.assertRaisesRegex(sqlite3.Error, "test failure"):
            self.build()
        with sqlite3.connect(self.index) as connection:
            content = connection.execute("SELECT content FROM sections").fetchall()
            self.assertFalse(any("Mudança" in row[0] for row in content))
            self.assertEqual(connection.execute("SELECT count(*) FROM documents").fetchone()[0], 2)
        self.assertEqual(index_status(self.root, self.catalog, self.index).status, "stale")

    def test_source_change_during_build_rolls_back(self) -> None:
        self.build()
        before = self.index.read_bytes()
        corpus = load_corpus(self.root, self.catalog)
        with patch("src.knowledge_index.load_corpus", side_effect=[corpus, None]):
            with self.assertRaisesRegex(KnowledgeError, "mudaram"):
                self.build()
        self.assertEqual(before, self.index.read_bytes())

    def test_search_accents_filters_and_provenance(self) -> None:
        self.build()
        for term in ("redação", "redacao", "sanitizacao"):
            with self.subTest(term=term):
                result = self.query(term)
                hit = result["results"][0]
                self.assertEqual(hit["path"], "reference.md")
                self.assertEqual(hit["heading"], "Arquitetura > Redação")
                self.assertEqual((hit["start_line"], hit["end_line"]), (3, 4))
                self.assertIsNone(hit["document_date"])
                self.assertEqual(hit["verification"], "unverified")
        self.assertEqual(len(self.query("eventos", component="runtime")["results"]), 1)
        self.assertEqual(self.query("eventos", component="other")["results"], [])
        self.assertEqual(len(self.query("eventos", kind=DocumentKind.HISTORICAL_EVIDENCE)["results"]), 1)
        self.assertEqual(self.query("eventos", kind=DocumentKind.PROPOSAL)["results"], [])

    def test_search_canonical_unicode_equivalence(self) -> None:
        original = (self.root / "reference.md").read_text(encoding="utf-8")
        for source_form in ("NFC", "NFD"):
            (self.root / "reference.md").write_text(
                unicodedata.normalize(source_form, original), encoding="utf-8",
            )
            self.build()
            for term in ("redação", "sanitização", "sensíveis"):
                for query_form in ("NFC", "NFD"):
                    with self.subTest(source_form=source_form, term=term, query_form=query_form):
                        result = self.query(unicodedata.normalize(query_form, term))
                        self.assertEqual(len(result["results"]), 1)
                        self.assertEqual(result["results"][0]["path"], "reference.md")

    def test_literal_query_cannot_execute_fts_operators_or_sql(self) -> None:
        self.build()
        for query in ('"redação" OR *', "redação'; DROP TABLE documents; --", "title:redação"):
            with self.subTest(query=query):
                self.assertTrue(self.query(query)["results"])
        self.assertEqual(index_status(self.root, self.catalog, self.index).documents, 2)

    def test_invalid_query_and_limits_are_errors(self) -> None:
        self.build()
        for query in ("", "  ", '"*():', "a" * 1001):
            with self.subTest(query=query):
                self.assertEqual(self.cli("search", query)[0], 2)
        for options in (["--limit", "0"], ["--limit", "21"], ["--max-chars", "511"],
                        ["--max-chars", "24001"], ["--kind", "unknown"], ["--component", ""]):
            with self.subTest(options=options):
                self.assertEqual(self.cli("search", "eventos", *options)[0], 2)

    def test_duplicate_sections_are_removed(self) -> None:
        self.add_document("copy.md", (self.root / "history.md").read_text(encoding="utf-8"))
        self.write_catalog()
        self.build()
        self.assertEqual(len(self.query("eventos")["results"]), 1)

    def test_verified_reference_wins_exact_relevance_tie(self) -> None:
        self.entries[0]["kind"] = "proposal"
        self.add_document("verified.md", (self.root / "reference.md").read_text(encoding="utf-8"))
        self.entries[-1]["verification"] = "verified"
        self.entries[-1]["last_verified"] = "2026-10-17"
        self.write_catalog()
        self.build()
        self.assertEqual(self.query("redação")["results"][0]["path"], "verified.md")

    def test_json_budget_counts_complete_response_and_newline(self) -> None:
        self.build()
        for budget in (512, 800, 1200, 24000):
            with self.subTest(budget=budget):
                response = self.query("arquitetura eventos", max_chars=budget, limit=1)
                self.assertLessEqual(len(encode_json(response)) + 1, budget)
                self.assertLessEqual(len(response["results"]), 1)
        (self.root / "reference.md").write_text(
            "# Redação\n" + "Sanitização de dados sensíveis. " * 50, encoding="utf-8",
        )
        self.build()
        code, response = self.cli("search", "redação", "--max-chars", "512")
        self.assertEqual(code, 3)
        self.assertEqual(response["status"], "budget_exhausted")
        self.assertTrue(response["truncated"])

    def test_no_match_is_distinct_from_failure(self) -> None:
        self.build()
        code, response = self.cli("search", "inexistente987")
        self.assertEqual(code, 0)
        self.assertEqual(response["results"], [])
        self.assertFalse(response["truncated"])

    def test_catalog_validation(self) -> None:
        mutations = [
            {"path": "../outside.md"}, {"path": "/absolute.md"}, {"path": "a\\b.md"},
            {"path": "./reference.md"}, {"path": "reference.txt"},
            {"component": ""}, {"kind": "random"}, {"verification": "random"},
            {"document_date": "not-a-date"}, {"document_date": "20260730"},
            {"verification": "verified"}, {"last_verified": "2026-10-17"},
        ]
        original = self.entries[0].copy()
        for change in mutations:
            with self.subTest(change=change):
                self.entries[0] = {**original, **change}
                self.write_catalog()
                with self.assertRaises((KnowledgeError, ValueError)):
                    load_corpus(self.root, self.catalog)
        self.entries[0] = original
        self.entries.append(original.copy())
        self.write_catalog()
        with self.assertRaisesRegex(KnowledgeError, "duplicado"):
            load_corpus(self.root, self.catalog)
        self.entries.pop()
        del self.entries[0]["last_verified"]
        self.write_catalog()
        with self.assertRaisesRegex(KnowledgeError, "ausentes"):
            load_corpus(self.root, self.catalog)

    def test_catalog_root_and_shape_validation(self) -> None:
        for payload in ([], {}, {"schema_version": True, "documents": []},
                        {"schema_version": 2, "documents": []},
                        {"schema_version": 1, "documents": [False]}):
            with self.subTest(payload=payload):
                self.catalog.write_text(json.dumps(payload))
                with self.assertRaises(KnowledgeError):
                    load_corpus(self.root, self.catalog)

    def test_symlink_escape_and_duplicate_resolved_path_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "outside.md"
            target.write_text("private")
            (self.root / "link.md").symlink_to(target)
            self.entries[0]["path"] = "link.md"
            self.write_catalog()
            with self.assertRaisesRegex(KnowledgeError, "fora"):
                load_corpus(self.root, self.catalog)
        (self.root / "alias.md").symlink_to(self.root / "history.md")
        self.entries[0]["path"] = "alias.md"
        self.write_catalog()
        with self.assertRaisesRegex(KnowledgeError, "duplicado"):
            load_corpus(self.root, self.catalog)

    def test_unlisted_documents_are_not_indexed(self) -> None:
        (self.root / "private.md").write_text("secretidentifier", encoding="utf-8")
        self.build()
        self.assertEqual(self.query("secretidentifier")["results"], [])

    def test_cannot_overwrite_sources_or_operational_database(self) -> None:
        for target in (self.catalog, self.root / "reference.md"):
            before = target.read_bytes()
            with self.assertRaises(KnowledgeError):
                build_index(self.root, self.catalog, target)
            self.assertEqual(target.read_bytes(), before)
        self.index.parent.mkdir()
        with sqlite3.connect(self.index) as connection:
            connection.execute("CREATE TABLE operational(id INTEGER)")
        before = self.index.read_bytes()
        with self.assertRaises(KnowledgeError):
            self.build()
        self.assertEqual(self.index.read_bytes(), before)

    def test_incompatible_and_corrupt_index_fail_explicitly(self) -> None:
        self.build()
        with sqlite3.connect(self.index) as connection:
            connection.execute("PRAGMA user_version=999")
        self.assertEqual(self.cli("status")[0], 2)
        self.assertEqual(self.cli("index")[0], 2)
        self.index.write_bytes(b"not a database")
        code, response = self.cli("search", "eventos")
        self.assertEqual(code, 2)
        self.assertEqual(response["error_type"], "DatabaseError")

    def test_incomplete_metadata_is_not_current(self) -> None:
        self.build()
        with sqlite3.connect(self.index) as connection:
            connection.execute("DELETE FROM metadata WHERE key='indexed_at'")
        code, response = self.cli("status")
        self.assertEqual(code, 2)
        self.assertIn("incompletos", response["message"])

    def test_index_cannot_be_reassigned_to_other_catalog(self) -> None:
        self.build()
        alias = self.root / "other.json"
        alias.write_bytes(self.catalog.read_bytes())
        with self.assertRaisesRegex(KnowledgeError, "outro"):
            build_index(self.root, alias, self.index)
        self.assertEqual(index_status(self.root, alias, self.index).status, "stale")

    def test_unavailable_fts5_is_reported(self) -> None:
        with patch("src.knowledge_index._initialize", side_effect=sqlite3.OperationalError("no such module: fts5")):
            code, response = self.cli("index")
        self.assertEqual(code, 2)
        self.assertIn("fts5", response["message"])

    def test_cli_json_round_trip_and_parser_errors(self) -> None:
        code, response = self.cli("index")
        self.assertEqual(code, 0)
        self.assertEqual(response["documents"], 2)
        self.assertEqual(self.cli("status")[1]["status"], "current")
        self.assertEqual(self.cli("search", "eventos")[1]["content_role"], "reference_not_instructions")
        for args in ([], ["unknown"], ["search"], ["search", "eventos", "--limit", "abc"]):
            with self.subTest(args=args):
                self.assertEqual(self.cli(*args)[0], 2)

    def test_import_has_no_api_or_database_side_effects(self) -> None:
        script = (
            "import sys; from src import knowledge_cli; "
            "assert 'api' not in sys.modules; assert 'sqlalchemy' not in sys.modules; "
            "assert 'streamlit' not in sys.modules"
        )
        subprocess.run([sys.executable, "-c", script], check=True,
                       cwd=Path(__file__).resolve().parents[1])


class MarkdownSectionTests(unittest.TestCase):
    def test_heading_keeps_hash_in_language_names(self) -> None:
        sections = extract_sections("# C#\n\n## F# ##\nExemplo.\n", "fallback")
        self.assertEqual(sections[0].title, "C#")
        self.assertEqual(sections[1].heading, "C# > F#")

    def test_fence_close_does_not_become_setext_heading(self) -> None:
        sections = extract_sections("# Guia\n```text\ncodigo\n```\n---\n", "fallback")
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].heading, "Guia")

    def test_fences_are_not_headings_and_lines_are_preserved(self) -> None:
        text = "# Guia\n\n## Código\n````python\n# not a heading\n```\n````\n\n## Final\nFim.\n"
        sections = extract_sections(text, "fallback")
        self.assertEqual([section.heading for section in sections], ["Guia", "Guia > Código", "Guia > Final"])
        self.assertEqual((sections[1].start_line, sections[1].end_line), (3, 8))
        self.assertIn("# not a heading", sections[1].content)
        lines = text.splitlines(keepends=True)
        for section in sections:
            self.assertEqual(section.content, "".join(lines[section.start_line - 1:section.end_line]))

    def test_setext_headings_preamble_and_empty_document(self) -> None:
        sections = extract_sections("Titulo\n======\n\nSubtitulo\n---------\ntexto\n", "fallback")
        self.assertEqual(sections[-1].heading, "Titulo > Subtitulo")
        self.assertEqual(extract_sections("", "fallback"), ())
        sections = extract_sections("Introducao\n\n# Guia\nTexto", "fallback")
        self.assertEqual((sections[0].start_line, sections[0].heading), (1, ""))
        self.assertEqual(sections[0].title, "Guia")

    def test_large_sections_and_long_lines_are_bounded_without_loss(self) -> None:
        for text in ("# Longo\n" + "Linha grande.\n" * 1000, "x" * 9000):
            with self.subTest(length=len(text)):
                sections = extract_sections(text, "fallback")
                self.assertTrue(all(len(section.content) <= CHUNK_CHARS for section in sections))
                self.assertEqual("".join(section.content for section in sections), text.rstrip("\n") + "\n")


class PilotAcceptanceTests(unittest.TestCase):
    def test_expected_sections_appear_in_top_three(self) -> None:
        root = Path(__file__).resolve().parents[2]
        catalog = root / "docs" / "observatory" / "catalog.json"
        cases = [
            ("Structured Runtime Observability Validation", "structured-runtime-observability", "Validation"),
            ("como funciona a sanitização de campos sensíveis", "observability-redaction-validation", "Validation"),
            ("Priority 4 typed contracts", "agent-mcp-observability-refactor-plan", "Priority 4"),
            ("como consultar o acervo", "docs/observatory/README.md", "Como consultar"),
            ("como usar a busca documental local", "kl_observatory/README.md", "Busca documental"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "pilot.sqlite3"
            report = build_index(root, catalog, index)
            self.assertEqual(report.documents, 6)
            for query, expected_path, heading in cases:
                with self.subTest(query=query):
                    results = search(root, catalog, index, query, limit=3)["results"]
                    self.assertTrue(any(expected_path in hit["path"] and heading in hit["heading"]
                                        for hit in results), results)
