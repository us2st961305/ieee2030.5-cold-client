"""
CLI entry point for BMS IEEE 2030.5 Web UI.

Usage:
    bms-web                     # Run on default port 5000
    bms-web --port 8080         # Run on custom port
    bms-web --debug             # Enable debug mode
    bms-web --config path.yaml  # Use custom config file
"""

import argparse
import logging
import sys

from bms_2030_5_client.web.app import create_app
from bms_2030_5_client.web.log_buffer import log_buffer
from bms_2030_5_client.logging_setup import setup_logging


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="BMS IEEE 2030.5 Client Web UI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start web UI on default port
  bms-web

  # Start on custom port
  bms-web --port 8080

  # Enable debug mode
  bms-web --debug

  # Use custom config file
  bms-web --config /path/to/runtime.yaml
        """,
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=5000,
        help="Port to listen on (default: 5000)",
    )
    
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="config/runtime.yaml",
        help="Path to runtime configuration file (default: config/runtime.yaml)",
    )
    
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug mode (auto-reload, verbose logging)",
    )
    
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="%(prog)s 0.1.0",
    )
    
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    # Load runtime config to get logging settings
    log_file = None
    buffer_size = 500
    max_bytes = 10 * 1024 * 1024
    backup_count = 5
    try:
        from bms_2030_5_client.runtime_config import RuntimeConfig
        rt = RuntimeConfig.from_yaml(args.config)
        log_file = rt.logging.file
        buffer_size = rt.logging.buffer_size
        max_bytes = rt.logging.max_bytes
        backup_count = rt.logging.backup_count
    except Exception:
        pass  # Fall back to defaults

    # Unified logging setup (structlog + file + rotation + buffer)
    setup_logging(
        level="DEBUG" if args.debug else "INFO",
        log_file=log_file,
        max_bytes=max_bytes,
        backup_count=backup_count,
        debug=args.debug,
        buffer_size=buffer_size,
    )
    
    logger = logging.getLogger(__name__)
    
    # Log startup
    log_buffer.add(
        f"Starting BMS Web UI on {args.host}:{args.port}",
        level="INFO",
        logger_name="web.cli",
    )
    
    # Create and run app
    app = create_app(
        config_path=args.config,
        debug=args.debug,
    )
    
    logger.info(f"Starting BMS Web UI at http://{args.host}:{args.port}")
    logger.info(f"Runtime config: {args.config}")
    
    try:
        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug,
            use_reloader=args.debug,
            threaded=True,
        )
        return 0
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        return 0
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
