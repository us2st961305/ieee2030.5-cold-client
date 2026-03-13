"""
CLI tool to unlock production mode for SafePowerController.

Generates a signed lockfile that SafePowerController verifies at startup.
This ensures production mode can only be enabled by someone with CLI access,
not through the Web UI.

Usage:
    bms-unlock-production --config config/runtime.yaml
    bms-unlock-production --revoke
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Lockfile lives next to the data directory
_DEFAULT_LOCKFILE = "data/.production_unlock"


def _get_lockfile_path(base_dir: str | None = None) -> Path:
    """Resolve absolute path to lockfile."""
    if base_dir:
        return Path(base_dir) / ".production_unlock"
    return Path(_DEFAULT_LOCKFILE)


def _compute_signature(safety_token: str, hostname: str, timestamp: str) -> str:
    """
    Compute HMAC-SHA256 signature over hostname + timestamp.

    Args:
        safety_token: The secret token from runtime.yaml.
        hostname: Machine hostname bound to the lockfile.
        timestamp: ISO-8601 creation timestamp.

    Returns:
        Hex-encoded HMAC-SHA256 digest.
    """
    message = f"{hostname}|{timestamp}".encode()
    return hmac.new(
        safety_token.encode(), message, hashlib.sha256
    ).hexdigest()


def verify_lockfile(safety_token: str, lockfile_path: str | Path | None = None) -> bool:
    """
    Verify that a valid production lockfile exists.

    Args:
        safety_token: The expected safety token (from runtime.yaml or env).
        lockfile_path: Override lockfile location (for testing).

    Returns:
        True if lockfile is valid and signature matches.
    """
    path = Path(lockfile_path) if lockfile_path else _get_lockfile_path()
    if not path.is_file():
        return False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    hostname = data.get("hostname", "")
    timestamp = data.get("timestamp", "")
    signature = data.get("signature", "")

    if not all([hostname, timestamp, signature]):
        return False

    # Verify hostname matches current machine
    if hostname != platform.node():
        logger.warning(
            "Lockfile hostname mismatch: lockfile=%s, current=%s",
            hostname, platform.node(),
        )
        return False

    expected_sig = _compute_signature(safety_token, hostname, timestamp)
    return hmac.compare_digest(signature, expected_sig)


def create_lockfile(safety_token: str, lockfile_path: str | Path | None = None) -> Path:
    """
    Create a signed production lockfile.

    Args:
        safety_token: The secret token to sign with.
        lockfile_path: Override lockfile location (for testing).

    Returns:
        Path to the created lockfile.
    """
    path = Path(lockfile_path) if lockfile_path else _get_lockfile_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    hostname = platform.node()
    timestamp = datetime.now(timezone.utc).isoformat()
    signature = _compute_signature(safety_token, hostname, timestamp)

    payload = {
        "hostname": hostname,
        "timestamp": timestamp,
        "signature": signature,
        "created_by": os.getenv("USER", "unknown"),
    }

    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # Restrict permissions: owner read/write only
    path.chmod(0o600)
    return path


def revoke_lockfile(lockfile_path: str | Path | None = None) -> bool:
    """
    Remove the production lockfile.

    Returns:
        True if file was removed, False if it didn't exist.
    """
    path = Path(lockfile_path) if lockfile_path else _get_lockfile_path()
    if path.is_file():
        path.unlink()
        return True
    return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Unlock production mode for BMS IEEE 2030.5 Power Control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This command generates a signed lockfile that SafePowerController
checks at startup. Production mode cannot be enabled without it.

Examples:
  # Unlock production mode (reads token from runtime.yaml)
  bms-unlock-production --config config/runtime.yaml

  # Revoke production unlock
  bms-unlock-production --revoke

  # Check current status
  bms-unlock-production --status
        """,
    )

    parser.add_argument(
        "--config", "-c",
        type=str,
        default="config/runtime.yaml",
        help="Path to runtime configuration file (default: config/runtime.yaml)",
    )
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Revoke production unlock (delete lockfile)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current production unlock status",
    )

    return parser.parse_args(argv)


def _load_safety_token(config_path: str) -> str | None:
    """Load safety_token from runtime.yaml."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        print(f"Error reading config: {e}", file=sys.stderr)
        return None

    token = (
        data.get("power_control", {})
        .get("production_auth", {})
        .get("safety_token", "")
    )
    return token if token else None


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    lockfile = _get_lockfile_path()

    # --- Status ---
    if args.status:
        if not lockfile.is_file():
            print(f"Status: LOCKED (no lockfile at {lockfile})")
            return 0
        try:
            data = json.loads(lockfile.read_text(encoding="utf-8"))
            print(f"Status: UNLOCKED")
            print(f"  Hostname:   {data.get('hostname', '?')}")
            print(f"  Timestamp:  {data.get('timestamp', '?')}")
            print(f"  Created by: {data.get('created_by', '?')}")

            token = _load_safety_token(args.config)
            if token:
                valid = verify_lockfile(token)
                print(f"  Valid:      {'Yes' if valid else 'No (signature mismatch or hostname changed)'}")
            else:
                print(f"  Valid:      Unknown (cannot load safety_token from config)")
        except (json.JSONDecodeError, OSError) as e:
            print(f"Status: ERROR reading lockfile: {e}")
        return 0

    # --- Revoke ---
    if args.revoke:
        if revoke_lockfile():
            print(f"Production unlock revoked (deleted {lockfile})")
        else:
            print("No lockfile found — production mode was not unlocked")
        return 0

    # --- Unlock ---
    token = _load_safety_token(args.config)
    if not token:
        print(
            "Error: No safety_token configured.\n"
            "Set power_control.production_auth.safety_token in your runtime.yaml first.",
            file=sys.stderr,
        )
        return 1

    # Interactive confirmation
    print("=" * 60)
    print("  WARNING: You are about to unlock PRODUCTION mode.")
    print("  This allows SafePowerController to write to PCS.")
    print("=" * 60)
    print(f"  Config:   {args.config}")
    print(f"  Hostname: {platform.node()}")
    print(f"  Lockfile: {lockfile}")
    print()

    confirm = input("Type 'YES' to confirm: ").strip()
    if confirm != "YES":
        print("Aborted.")
        return 1

    path = create_lockfile(token)
    print(f"\nProduction mode unlocked. Lockfile written to: {path}")
    print("Restart the service for changes to take effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
