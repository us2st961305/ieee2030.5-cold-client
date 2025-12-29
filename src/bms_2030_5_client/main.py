"""
Main entry point for BMS IEEE 2030.5 Client.
"""

import argparse
import asyncio
import logging
import sys
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
Examples:
  # Start with default config
  bms-client

  # Start with custom config file
  bms-client --config /path/to/config.yaml

  # Debug mode
  bms-client --debug

  # Disable metering (only DER status reporting)
  bms-client --no-metering

  # Generate sample config
  bms-client --generate-config sample_config.yaml
        """,
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
    
    # Check config file exists
    config_path = Path(args.config)
    if not config_path.exists():
        logging.error(f"Configuration file not found: {config_path}")
        logging.info("Use --generate-config to create a sample configuration")
        return 1
    
    # Run client
    try:
        asyncio.run(run_client(
            str(config_path),
            auto_register=not args.no_register,
            enable_metering=not args.no_metering,
        ))
        return 0
    except Exception as e:
        logging.exception(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
