"""
Main entry point for BMS IEEE 2030.5 Client.

Supports multiple modes:
- client: Run automation client only
- web: Run web UI only
- all: Run both web UI and client (default)
"""

import argparse
import asyncio
import logging
import sys
import threading
from pathlib import Path

from bms_2030_5_client.client import BMSClient
from bms_2030_5_client.config import Config


def setup_logging(level: str = "INFO", log_file: str = None) -> None:
    """Configure logging."""
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="IEEE 2030.5 BMS Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  all     - Run web UI + automation client (default)
  web     - Run web UI only (control client via dashboard)
  client  - Run automation client only (no web UI)

Examples:
  # Start with web UI + client (default mode)
  bms-client

  # Start web UI only (control via dashboard)
  bms-client --mode web

  # Start client only (no web UI)
  bms-client --mode client

  # Custom config file
  bms-client --config /path/to/config.yaml

  # Custom web port
  bms-client --mode web --port 8080

  # Generate sample config
  bms-client --generate-config sample_config.yaml
        """,
    )
    
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["all", "web", "client"],
        default="all",
        help="Execution mode: all, web, or client (default: all)",
    )
    
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="config/config.yaml",
        help="Path to configuration file (default: config/config.yaml)",
    )
    
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging",
    )
    
    parser.add_argument(
        "--generate-config",
        type=str,
        metavar="PATH",
        help="Generate sample configuration file and exit",
    )
    
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="Don't auto-register with IEEE 2030.5 server",
    )
    
    parser.add_argument(
        "--no-metering",
        action="store_true",
        help="Disable meter data upload (MirrorUsagePoint)",
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Web server host (default: 0.0.0.0)",
    )
    
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=5000,
        help="Web server port (default: 5000)",
    )
    
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="%(prog)s 0.1.0",
    )

    return parser.parse_args()


async def run_client(
    config_path: str,
    auto_register: bool = True,
    enable_metering: bool = True,
) -> None:
    """Run the BMS client."""
    config = Config.from_yaml(config_path)
    client = BMSClient(
        config,
        auto_register=auto_register,
        enable_metering=enable_metering,
    )
    
    try:
        await client.run_forever()
    except KeyboardInterrupt:
        logging.info("Received interrupt signal")
    finally:
        await client.stop()


def run_web_server(host: str, port: int, debug: bool = False) -> None:
    """Run the Flask web server."""
    from bms_2030_5_client.web.app import create_app
    
    app = create_app()
    app.run(host=host, port=port, debug=debug, use_reloader=False)


def run_unified(
    config_path: str,
    host: str,
    port: int,
    auto_register: bool = True,
    enable_metering: bool = True,
    debug: bool = False,
) -> None:
    """
    Run both web server and client.
    
    The web server runs in a background thread while
    the client manager provides control via the dashboard.
    """
    from bms_2030_5_client.web.app import create_app
    from bms_2030_5_client.web.client_manager import get_client_manager
    
    # Configure client manager
    client_manager = get_client_manager()
    client_manager.configure(
        config_path=config_path,
        auto_register=auto_register,
        enable_metering=enable_metering,
    )
    
    # Auto-start client
    logging.info("Auto-starting BMSClient...")
    client_manager.start()
    
    # Create Flask app
    app = create_app()
    
    # Run web server (blocking)
    logging.info(f"Starting web server on http://{host}:{port}")
    try:
        app.run(host=host, port=port, debug=debug, use_reloader=False)
    finally:
        # Stop client when web server exits
        client_manager.stop()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    # Generate config if requested
    if args.generate_config:
        config = Config()
        config.to_yaml(args.generate_config)
        print(f"Generated sample configuration: {args.generate_config}")
        return 0
    
    # Setup logging
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(level=log_level)
    
    # Check config file exists (not required for web-only mode)
    config_path = Path(args.config)
    if args.mode != "web" and not config_path.exists():
        logging.error(f"Configuration file not found: {config_path}")
        logging.info("Use --generate-config to create a sample configuration")
        return 1
    
    # Run based on mode
    try:
        if args.mode == "client":
            # Client only mode
            logging.info("Starting in client-only mode...")
            asyncio.run(run_client(
                str(config_path),
                auto_register=not args.no_register,
                enable_metering=not args.no_metering,
            ))
        elif args.mode == "web":
            # Web only mode
            logging.info("Starting in web-only mode...")
            run_web_server(
                host=args.host,
                port=args.port,
                debug=args.debug,
            )
        else:
            # Unified mode (default)
            logging.info("Starting in unified mode (web + client)...")
            run_unified(
                config_path=str(config_path),
                host=args.host,
                port=args.port,
                auto_register=not args.no_register,
                enable_metering=not args.no_metering,
                debug=args.debug,
            )
        return 0
    except Exception as e:
        logging.exception(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
