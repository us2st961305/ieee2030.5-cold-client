#!/usr/bin/env python3
"""
Write a work log entry to ChromaDB copilot_work_log collection.

Usage:
    python scripts/chromadb_write_log.py \
        --summary "One line summary" \
        --files "file1.py, file2.py" \
        --tags "tag1, tag2" \
        --anchors "file.py::Class::method" \
        --deps "module_a.py, module_b.py" \
        --rationale "Why this approach" \
        --risk "Known risks" \
        --type feature \
        --details "Detailed description"
"""
import argparse
import os
import sys
import uuid
from datetime import datetime, timezone


def get_chromadb_client():
    """Create ChromaDB client from environment variables."""
    try:
        import chromadb
    except ImportError:
        print("ERROR: chromadb not installed. Run: pip install chromadb")
        sys.exit(1)

    host = os.environ.get("CHROMA_HOST")
    token = os.environ.get("CHROMA_AUTH_TOKEN")

    if not host or not token:
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        os.environ.setdefault(key.strip(), val.strip())
            host = os.environ.get("CHROMA_HOST")
            token = os.environ.get("CHROMA_AUTH_TOKEN")

    if not host or not token:
        print("ERROR: CHROMA_HOST and CHROMA_AUTH_TOKEN must be set")
        sys.exit(1)

    return chromadb.HttpClient(
        host=host,
        port=443,
        ssl=True,
        headers={"Authorization": f"Bearer {token}"},
    )


def write_log(args):
    """Write a structured log entry to copilot_work_log."""
    client = get_chromadb_client()
    collection = client.get_collection("copilot_work_log")

    # Build structured document
    sections = [f"[ieee2030.5-cold-client] {args.summary}", ""]
    if args.anchors:
        sections.append("## Code Anchors")
        for anchor in args.anchors.split(","):
            sections.append(f"- {anchor.strip()}")
        sections.append("")
    if args.deps:
        sections.append("## Dependencies Affected")
        for dep in args.deps.split(","):
            sections.append(f"- {dep.strip()}")
        sections.append("")
    if args.rationale:
        sections.append("## Decision Rationale")
        sections.append(args.rationale)
        sections.append("")
    if args.risk:
        sections.append("## Risk Notes")
        sections.append(args.risk)
        sections.append("")
    if args.details:
        sections.append("## Details")
        sections.append(args.details)
        sections.append("")

    sections.append(f"Files: {args.files}")
    sections.append(f"Tags: {args.tags}")

    document = "\n".join(sections)
    doc_id = str(uuid.uuid4())

    metadata = {
        "project_name": "ieee2030.5-cold-client",
        "project_path": "/home/us2st/ieee2030.5-cold-client",
        "summary": args.summary,
        "files_changed": args.files,
        "tags": args.tags,
        "github_repo": "us2st/ieee2030.5-cold-client",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "code_anchors": args.anchors or "",
        "dependencies_affected": args.deps or "",
        "decision_rationale": args.rationale or "",
        "risk_notes": args.risk or "",
        "change_type": args.type,
    }

    collection.add(ids=[doc_id], documents=[document], metadatas=[metadata])
    print(f"Written to copilot_work_log: {doc_id}")
    print(f"Summary: {args.summary}")


def main():
    parser = argparse.ArgumentParser(description="Write to ChromaDB copilot_work_log")
    parser.add_argument("--summary", required=True, help="One-line summary")
    parser.add_argument("--files", required=True, help="Comma-separated changed files")
    parser.add_argument("--tags", required=True, help="Comma-separated tags")
    parser.add_argument("--anchors", default="", help="Comma-separated code anchors (file.py::Class::method)")
    parser.add_argument("--deps", default="", help="Comma-separated affected dependencies")
    parser.add_argument("--rationale", default="", help="Decision rationale")
    parser.add_argument("--risk", default="", help="Risk notes")
    parser.add_argument("--type", default="feature", choices=["feature", "bugfix", "refactor", "config", "fix"], help="Change type")
    parser.add_argument("--details", default="", help="Detailed description")
    args = parser.parse_args()
    write_log(args)


if __name__ == "__main__":
    main()
