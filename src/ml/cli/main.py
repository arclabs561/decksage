#!/usr/bin/env python3
"""
DeckSage CLI - Command-line interface for card similarity API

Usage:
    decksage similar "Lightning Bolt" --k 5
    decksage search "lightning" --output json
    decksage health
    decksage ready
    decksage list --prefix "Light" --limit 20
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .client import DeckSageClient


def format_table(results: list[dict[str, Any]]) -> str:
    """Format results as a table."""
    lines = []
    lines.append("Card".ljust(40) + "Similarity")
    lines.append("-" * 50)
    for r in results:
        card = r.get("card", r.get("card_name", ""))
        score = r.get("similarity", r.get("score", 0.0))
        lines.append(card.ljust(40) + f"{score:.4f}")
    return "\n".join(lines)


def format_simple(results: list[dict[str, Any]]) -> str:
    """Format results as simple list."""
    lines = []
    for r in results:
        card = r.get("card", r.get("card_name", ""))
        score = r.get("similarity", r.get("score", 0.0))
        lines.append(f"{card} ({score:.4f})")
    return "\n".join(lines)


def cmd_health(client: DeckSageClient, args: argparse.Namespace) -> int:
    """Health check command."""
    try:
        health = client.health()
        if args.output == "json":
            print(json.dumps(health, indent=2))
        else:
            print(f"Status: {health['status']}")
            print(f"Cards: {health.get('num_cards', 0):,}")
            print(f"Embedding Dim: {health.get('embedding_dim', 0)}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_ready(client: DeckSageClient, args: argparse.Namespace) -> int:
    """Readiness check command."""
    try:
        ready = client.ready()
        if args.output == "json":
            print(json.dumps(ready, indent=2))
        else:
            print(f"Status: {ready.get('status', 'unknown')}")
            methods = ready.get("available_methods", [])
            print(f"Available methods: {', '.join(methods)}")
            if "fusion_default_weights" in ready:
                print(f"Fusion weights: {json.dumps(ready['fusion_default_weights'])}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_similar(client: DeckSageClient, args: argparse.Namespace) -> int:
    """Find similar cards command."""
    if not args.card:
        print("Error: card name required", file=sys.stderr)
        return 1

    try:
        result = client.find_similar(
            card_name=args.card,
            k=args.k,
            mode=args.mode or "substitute",
        )
        results = result.get("results", [])

        if args.output == "json":
            print(json.dumps(result, indent=2))
        elif args.output == "simple":
            print(format_simple(results))
        else:
            print(f"Similar to: {result.get('query', args.card)}")
            print(format_table(results))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_search(client: DeckSageClient, args: argparse.Namespace) -> int:
    """Search cards command."""
    if not args.query:
        print("Error: search query required", file=sys.stderr)
        return 1

    try:
        result = client.search(
            query=args.query,
            limit=args.limit,
            text_weight=args.text_weight,
            vector_weight=args.vector_weight,
        )
        results = result.get("results", [])

        if args.output == "json":
            print(json.dumps(result, indent=2))
        elif args.output == "simple":
            print(format_simple(results))
        else:
            print(f"Search results for: {args.query}")
            for r in results:
                card = r.get("card_name", "")
                score = r.get("score", 0.0)
                source = r.get("source", "")
                print(f"  {card.ljust(40)} {score:.4f} ({source})")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_list(client: DeckSageClient, args: argparse.Namespace) -> int:
    """List cards command."""
    try:
        result = client.list_cards(prefix=args.prefix, limit=args.limit, offset=args.offset)
        items = result.get("items", [])
        total = result.get("total", 0)

        if args.output == "json":
            print(json.dumps(result, indent=2))
        else:
            print(f"Total cards: {total}")
            for item in items:
                print(item)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="DeckSage CLI - Card Similarity API Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  decksage similar "Lightning Bolt" --k 5
  decksage search "lightning" --output json
  decksage health
  decksage list --prefix "Light" --limit 20
        """,
    )

    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Use direct API imports (faster, local only)",
    )
    parser.add_argument(
        "--output",
        choices=["json", "table", "simple"],
        default="table",
        help="Output format (default: table)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Health command
    subparsers.add_parser("health", help="Check API health")

    # Ready command
    subparsers.add_parser("ready", help="Check API readiness")

    # Similar command
    similar_parser = subparsers.add_parser("similar", help="Find similar cards")
    similar_parser.add_argument("card", help="Card name")
    similar_parser.add_argument("--k", type=int, default=10, help="Number of results (default: 10)")
    similar_parser.add_argument(
        "--mode",
        choices=["substitute", "synergy", "meta", "fusion", "embedding", "jaccard"],
        help="Similarity mode",
    )

    # Search command
    search_parser = subparsers.add_parser("search", help="Search cards")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--limit", type=int, default=10, help="Number of results (default: 10)"
    )
    search_parser.add_argument(
        "--text-weight", type=float, default=0.5, help="Text search weight (default: 0.5)"
    )
    search_parser.add_argument(
        "--vector-weight", type=float, default=0.5, help="Vector search weight (default: 0.5)"
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List available cards")
    list_parser.add_argument("--prefix", help="Filter by prefix")
    list_parser.add_argument(
        "--limit", type=int, default=100, help="Number of results (default: 100)"
    )
    list_parser.add_argument(
        "--offset", type=int, default=0, help="Offset for pagination (default: 0)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Create client
    client = DeckSageClient(base_url=args.url, direct_mode=args.direct)

    # Route to command handler
    handlers = {
        "health": cmd_health,
        "ready": cmd_ready,
        "similar": cmd_similar,
        "search": cmd_search,
        "list": cmd_list,
    }

    handler = handlers.get(args.command)
    if not handler:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1

    return handler(client, args)


if __name__ == "__main__":
    sys.exit(main())
