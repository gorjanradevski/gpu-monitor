#!/usr/bin/env python3
"""Command line interface for GPU Monitor."""

import argparse
import sys

from gpu_monitor.monitor import run_server


def main():
    """Main entry point for the gpu_monitor command."""
    parser = argparse.ArgumentParser(
        description="GPU monitoring tool for cluster hosts",
        prog="gpu_monitor"
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0"
    )

    parser.add_argument(
        "--config",
        help="Show current configuration and exit",
        action="store_true"
    )

    args = parser.parse_args()

    if args.config:
        show_config()
        sys.exit(0)

    # Run the server
    run_server()


def show_config():
    """Show current configuration."""
    from gpu_monitor.config import load_config

    config = load_config()
    print("GPU Monitor Configuration:")
    print("=" * 50)
    print(f"Hosts: {', '.join(config['hosts'])}")
    print(f"Poll interval: {config['poll_interval']} seconds")
    print(f"Bind host: {config['bind_host']}")
    print(f"Bind port: {config['bind_port']}")
    print(f"SSH config path: {config['ssh_config_path']}")


if __name__ == "__main__":
    main()