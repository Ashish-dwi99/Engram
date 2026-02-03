#!/usr/bin/env python3
"""Engram CLI - Command line interface for the Engram memory layer.

Usage:
    engram install          Install MCP server to Claude Code, Codex
    engram add "content"    Add a memory from command line
    engram search "query"   Search memories
    engram list             List all memories
    engram stats            Show memory statistics
    engram decay            Apply memory decay (forgetting)
    engram export           Export memories to JSON
    engram server           Start the REST API server
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


def cmd_install(args):
    """Install Engram MCP server to agent configurations."""
    from engram.cli import install
    install()


def cmd_add(args):
    """Add a memory from the command line."""
    from engram import Engram

    memory = Engram(in_memory=False)
    result = memory.add(
        content=args.content,
        user_id=args.user_id,
        infer=not args.no_infer,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        count = len(result.get("results", []))
        print(f"Added {count} memory(ies)")
        for r in result.get("results", []):
            print(f"  ID: {r.get('id', 'N/A')}")


def cmd_search(args):
    """Search memories."""
    from engram import Engram

    memory = Engram(in_memory=False)
    results = memory.search(
        query=args.query,
        user_id=args.user_id,
        limit=args.limit,
    )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"Found {len(results)} result(s):\n")
        for i, r in enumerate(results, 1):
            score = r.get("score", r.get("composite_score", 0))
            content = r.get("memory", r.get("content", ""))
            layer = r.get("layer", "sml")
            print(f"{i}. [{layer}] (score: {score:.3f})")
            print(f"   {content[:100]}{'...' if len(content) > 100 else ''}")
            print()


def cmd_list(args):
    """List all memories."""
    from engram import Engram

    memory = Engram(in_memory=False)
    results = memory.get_all(
        user_id=args.user_id,
        layer=args.layer,
        limit=args.limit,
    )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"Total: {len(results)} memories\n")
        for r in results:
            mem_id = r.get("id", "N/A")[:8]
            content = r.get("memory", r.get("content", ""))
            layer = r.get("layer", "sml")
            strength = r.get("strength", 1.0)
            print(f"[{mem_id}...] [{layer}] (str: {strength:.2f})")
            print(f"  {content[:80]}{'...' if len(content) > 80 else ''}")


def cmd_stats(args):
    """Show memory statistics."""
    from engram import Engram

    memory = Engram(in_memory=False)
    stats = memory.stats(user_id=args.user_id)

    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print("Engram Memory Statistics")
        print("=" * 40)
        print(f"Total memories:  {stats.get('total', 0)}")
        print(f"Short-term (SML): {stats.get('sml_count', 0)}")
        print(f"Long-term (LML):  {stats.get('lml_count', 0)}")

        categories = stats.get("categories", {})
        if categories:
            print(f"\nCategories ({len(categories)}):")
            for cat, count in sorted(categories.items(), key=lambda x: -x[1])[:10]:
                print(f"  {cat}: {count}")


def cmd_decay(args):
    """Apply memory decay (forgetting)."""
    from engram import Engram

    if args.dry_run:
        print("Dry run - showing what would be decayed...")
        print("(Full dry-run not yet implemented, running actual decay)")

    memory = Engram(in_memory=False)
    result = memory.forget(user_id=args.user_id)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Decay Applied:")
        print(f"  Decayed:   {result.get('decayed', 0)} memories")
        print(f"  Forgotten: {result.get('forgotten', 0)} memories")
        print(f"  Promoted:  {result.get('promoted', 0)} memories")


def cmd_export(args):
    """Export memories to JSON."""
    from engram import Engram

    memory = Engram(in_memory=False)
    results = memory.get_all(
        user_id=args.user_id,
        limit=10000,  # Export all
    )

    export_data = {
        "version": "1.0",
        "user_id": args.user_id,
        "count": len(results),
        "memories": results,
    }

    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2)
        print(f"Exported {len(results)} memories to {output_path}")
    else:
        print(json.dumps(export_data, indent=2))


def cmd_server(args):
    """Start the REST API server."""
    from engram.api.server import run
    sys.argv = ["engram-api", "--host", args.host, "--port", str(args.port)]
    if args.reload:
        sys.argv.append("--reload")
    run()


def cmd_categories(args):
    """List categories."""
    from engram import Engram

    memory = Engram(in_memory=False)
    categories = memory.categories()

    if args.json:
        print(json.dumps(categories, indent=2))
    else:
        print(f"Categories ({len(categories)}):\n")
        for cat in categories:
            cat_id = cat.get("id", "N/A")
            name = cat.get("name", cat_id)
            count = cat.get("memory_count", 0)
            print(f"  {name} ({count} memories)")


def main():
    parser = argparse.ArgumentParser(
        prog="engram",
        description="Engram - Bio-inspired memory layer for AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    engram install                    # Setup for Claude Code & Codex
    engram add "User prefers Python"  # Add a memory
    engram search "preferences"       # Search memories
    engram stats                      # View statistics
    engram server                     # Start REST API
        """,
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.2.0")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Install command
    p_install = subparsers.add_parser("install", help="Install MCP server to agents")

    # Add command
    p_add = subparsers.add_parser("add", help="Add a memory")
    p_add.add_argument("content", help="Memory content to store")
    p_add.add_argument("--user-id", "-u", default="default", help="User ID")
    p_add.add_argument("--no-infer", action="store_true", help="Don't extract facts")
    p_add.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    # Search command
    p_search = subparsers.add_parser("search", help="Search memories")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--user-id", "-u", default="default", help="User ID")
    p_search.add_argument("--limit", "-n", type=int, default=10, help="Max results")
    p_search.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    # List command
    p_list = subparsers.add_parser("list", help="List all memories")
    p_list.add_argument("--user-id", "-u", default="default", help="User ID")
    p_list.add_argument("--layer", "-l", choices=["sml", "lml"], help="Filter by layer")
    p_list.add_argument("--limit", "-n", type=int, default=50, help="Max results")
    p_list.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    # Stats command
    p_stats = subparsers.add_parser("stats", help="Show statistics")
    p_stats.add_argument("--user-id", "-u", default=None, help="User ID (all if not set)")
    p_stats.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    # Decay command
    p_decay = subparsers.add_parser("decay", help="Apply memory decay")
    p_decay.add_argument("--user-id", "-u", default=None, help="User ID")
    p_decay.add_argument("--dry-run", action="store_true", help="Preview without applying")
    p_decay.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    # Export command
    p_export = subparsers.add_parser("export", help="Export memories to JSON")
    p_export.add_argument("--user-id", "-u", default="default", help="User ID")
    p_export.add_argument("--output", "-o", help="Output file (stdout if not set)")

    # Categories command
    p_cats = subparsers.add_parser("categories", help="List categories")
    p_cats.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    # Server command
    p_server = subparsers.add_parser("server", help="Start REST API server")
    p_server.add_argument("--host", default="127.0.0.1", help="Host to bind")
    p_server.add_argument("--port", "-p", type=int, default=8100, help="Port")
    p_server.add_argument("--reload", action="store_true", help="Auto-reload on changes")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Dispatch to command handler
    commands = {
        "install": cmd_install,
        "add": cmd_add,
        "search": cmd_search,
        "list": cmd_list,
        "stats": cmd_stats,
        "decay": cmd_decay,
        "export": cmd_export,
        "categories": cmd_categories,
        "server": cmd_server,
    }

    handler = commands.get(args.command)
    if handler:
        try:
            handler(args)
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
