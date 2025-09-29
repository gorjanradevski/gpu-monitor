# GPU Monitor

Minimal GPU monitoring tool for cluster hosts with SSH access.

## Installation & Usage

After cloning the package, install the package via pip: `pip install .` Then, run the GPU monitor: `gpu_monitor`. The web interface will be available at http://localhost:8000

### Command line options

Show current configuration:
```bash
gpu_monitor --config
```

Show version:
```bash
gpu_monitor --version
```

## Configuration

Configure the tool by editing the `[tool.gpu-monitor]` section in `pyproject.toml`:

```toml
[tool.gpu-monitor]
# SSH monitoring configuration
hosts = [
    "c535",
    "c536",
    "c104",
    # Add your hosts here
]

# Server configuration
poll_interval = 5.0
bind_host = "127.0.0.1"
bind_port = 8000
ssh_config_path = "~/.ssh/config"
```

### Configuration options

- `hosts`: List of SSH host aliases to monitor
- `poll_interval`: Polling interval in seconds (default: 5.0)
- `bind_host`: Server bind address (default: 127.0.0.1)
- `bind_port`: Server port (default: 8000)
- `ssh_config_path`: SSH config file path (default: ~/.ssh/config)

Configuration can also be overridden via environment variables:
- `POLL_INTERVAL`
- `BIND_HOST`
- `BIND_PORT`
- `SSH_CONFIG_PATH`

## Requirements

- Python 3.11+
- SSH access to the target hosts
- nvidia-smi available on target hosts
- FastAPI and uvicorn (automatically installed)