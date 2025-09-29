"""Configuration management for GPU Monitor."""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def find_pyproject_toml() -> Path:
    """Find pyproject.toml file starting from current directory and going up."""
    current = Path.cwd()

    # First check current directory and parents
    for parent in [current] + list(current.parents):
        pyproject_path = parent / "pyproject.toml"
        if pyproject_path.exists():
            return pyproject_path

    # If not found in current directory tree, check if we're in an installed package
    # and look in the package directory
    try:
        import gpu_monitor
        package_dir = Path(gpu_monitor.__file__).parent.parent.parent
        pyproject_path = package_dir / "pyproject.toml"
        if pyproject_path.exists():
            return pyproject_path
    except ImportError:
        pass

    raise FileNotFoundError("Could not find pyproject.toml file")


def load_config() -> Dict[str, Any]:
    """Load configuration from pyproject.toml file."""
    try:
        pyproject_path = find_pyproject_toml()
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)

        config = data.get("tool", {}).get("gpu-monitor", {})

        # Set defaults if not in config
        defaults = {
            "hosts": ["localhost"],
            "poll_interval": 5.0,
            "bind_host": "127.0.0.1",
            "bind_port": 8000,
            "ssh_config_path": "~/.ssh/config"
        }

        for key, default_value in defaults.items():
            if key not in config:
                config[key] = default_value

        return config

    except FileNotFoundError:
        # Fallback to environment variables and defaults
        return {
            "hosts": ["localhost"],
            "poll_interval": float(os.environ.get("POLL_INTERVAL", "5.0")),
            "bind_host": os.environ.get("BIND_HOST", "127.0.0.1"),
            "bind_port": int(os.environ.get("BIND_PORT", "8000")),
            "ssh_config_path": os.environ.get("SSH_CONFIG_PATH", "~/.ssh/config")
        }


def get_hosts() -> List[str]:
    """Get list of hosts to monitor."""
    config = load_config()
    return config["hosts"]


def get_poll_interval() -> float:
    """Get polling interval in seconds."""
    config = load_config()
    return config["poll_interval"]


def get_bind_host() -> str:
    """Get bind host address."""
    config = load_config()
    return config["bind_host"]


def get_bind_port() -> int:
    """Get bind port."""
    config = load_config()
    return config["bind_port"]


def get_ssh_config_path() -> str:
    """Get SSH config file path."""
    config = load_config()
    return os.path.expanduser(config["ssh_config_path"])