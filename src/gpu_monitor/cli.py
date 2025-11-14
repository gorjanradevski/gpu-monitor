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
        "--servers",
        nargs="+",
        help="List of servers to monitor (overrides config file)",
        metavar="HOST"
    )

    args = parser.parse_args()

    show_config(args.servers)
    # Run the server
    run_server(args.servers)


def show_config(override_hosts=None):
    """Show current configuration."""
    from gpu_monitor.config import load_config

    config = load_config()

    # Use override hosts if provided
    hosts = override_hosts if override_hosts else config['hosts']

    print("GPU Monitor Configuration:")
    print("=" * 50)
    print(f"Hosts: {', '.join(hosts)}")
    if override_hosts:
        print("  (from command line)")
    print(f"Poll interval: {config['poll_interval']} seconds")
    print(f"Bind host: {config['bind_host']}")
    print(f"Bind port: {config['bind_port']}")
    print(f"SSH config path: {config['ssh_config_path']}")


if __name__ == "__main__":
    main()