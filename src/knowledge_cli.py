from __future__ import annotations

import argparse
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .knowledge_index import build_index, encode_json, index_status, search
from .knowledge_types import DocumentKind, KnowledgeError


class KnowledgeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise KnowledgeError(message)


def main(argv: list[str] | None = None) -> int:
    parser = KnowledgeParser(description="Busca documental local; nao executa instrucoes recuperadas.")
    parser.add_argument("--workspace-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--catalog", type=Path, default=Path("docs/observatory/catalog.json"))
    parser.add_argument("--index-path", type=Path,
                        default=Path(__file__).resolve().parents[1] / "var" / "knowledge.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("index", help="Indexar somente documentos do catalogo.")
    commands.add_parser("status", help="Verificar integridade e atualidade do indice.")
    query = commands.add_parser("search", help="Consultar trechos sem alterar o indice.")
    query.add_argument("query")
    query.add_argument("--limit", type=int, default=5)
    query.add_argument("--max-chars", type=int, default=12000)
    query.add_argument("--component")
    query.add_argument("--kind", choices=[kind.value for kind in DocumentKind])
    try:
        args = parser.parse_args(argv)
        root = args.workspace_root.resolve()
        catalog = root / args.catalog
        if args.command == "index":
            output = asdict(build_index(root, catalog, args.index_path))
        elif args.command == "status":
            status = index_status(root, catalog, args.index_path)
            print(encode_json(asdict(status)))
            return 0 if status.status == "current" else 3
        else:
            output = search(
                root, catalog, args.index_path, args.query,
                limit=args.limit, max_chars=args.max_chars, component=args.component,
                kind=DocumentKind(args.kind) if args.kind else None,
            )
        print(encode_json(output))
        return 0 if output["status"] != "budget_exhausted" else 3
    except (OSError, ValueError, sqlite3.Error, UnicodeError) as error:
        print(encode_json({
            "schema_version": 1, "status": "error",
            "error_type": type(error).__name__, "message": str(error),
        }))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
