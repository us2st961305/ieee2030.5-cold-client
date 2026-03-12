#!/usr/bin/env python3
"""
Search copilot_work_log in ChromaDB for historical records.

Usage:
    python scripts/chromadb_search.py "Modbus reconnection backoff"
    python scripts/chromadb_search.py "affected_file.py function description" --n 10
"""
import argparse
import os
import sys


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
        # Try loading from .env
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
        print("Set them in .env or as environment variables")
        sys.exit(1)

    return chromadb.HttpClient(
        host=host,
        port=443,
        ssl=True,
        headers={"Authorization": f"Bearer {token}"},
    )


def search(query: str, n_results: int = 5, collection_name: str = "copilot_work_log"):
    """Search ChromaDB collection and print results."""
    client = get_chromadb_client()
    collection = client.get_collection(collection_name)
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["metadatas", "documents", "distances"],
    )

    if not results["documents"][0]:
        print("No results found.")
        return

    for i, meta in enumerate(results["metadatas"][0]):
        dist = results["distances"][0][i]
        print(f"\n[{i}] {meta.get('summary', 'N/A')} (distance: {dist:.4f})")
        if meta.get("code_anchors"):
            print(f"    Anchors: {meta['code_anchors']}")
        if meta.get("decision_rationale"):
            print(f"    Decision: {meta['decision_rationale']}")
        if meta.get("risk_notes"):
            print(f"    ⚠️ Risk: {meta['risk_notes']}")
        if meta.get("files_changed"):
            print(f"    Files: {meta['files_changed']}")


def main():
    parser = argparse.ArgumentParser(description="Search ChromaDB copilot_work_log")
    parser.add_argument("query", help="Search query text")
    parser.add_argument("--n", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--collection", default="copilot_work_log", help="Collection name")
    args = parser.parse_args()
    search(args.query, args.n, args.collection)


if __name__ == "__main__":
    main()
