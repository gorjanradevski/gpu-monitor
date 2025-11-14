#!/usr/bin/env python3
"""
Minimal GPU monitor SSH'es into each host using the system ssh binary (so ProxyJump / IdentityFile are respected),
runs nvidia-smi, and serves a tiny web UI and JSON /metrics endpoint.
"""

import asyncio
import subprocess
import time
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from gpu_monitor.config import (
    get_bind_host,
    get_bind_port,
    get_hosts,
    get_poll_interval,
)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
latest: Dict[str, Dict[str, Any]] = {}  # host_alias -> payload


def parse_nvidia_smi_output(output: str) -> Dict[str, Any]:
    """
    Parse the combined output from nvidia-smi GPU query and compute-apps query.
    Returns dict with 'gpus' and 'users' lists.
    """
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]

    # Split output at the separator
    gpu_lines = []
    process_lines = []
    in_process_section = False

    for line in lines:
        if line == "---":
            in_process_section = True
            continue
        if in_process_section:
            process_lines.append(line)
        else:
            gpu_lines.append(line)

    # Parse GPU data
    gpus = []
    for ln in gpu_lines:
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) < 6:
            continue
        try:
            index = int(parts[0])
            name = parts[1]
            bus_id = parts[2]
            util = int(parts[3])
            mem_total = int(parts[4])
            mem_used = int(parts[5])
        except Exception:
            continue
        gpus.append({
            "index": index,
            "name": name,
            "bus_id": bus_id,
            "utilization_gpu": util,
            "memory_total_mib": mem_total,
            "memory_used_mib": mem_used,
        })

    # Parse process data from query-compute-apps output
    # Format: gpu_bus_id, pid, process_name, used_memory
    users = []

    # Create a mapping from GPU bus_id to GPU data
    gpu_bus_id_to_gpu = {}
    for gpu in gpus:
        gpu_bus_id_to_gpu[gpu['bus_id']] = gpu

    for line in process_lines:
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4:
            try:
                gpu_bus_id = parts[0]
                pid = int(parts[1])
                process_name = parts[2]
                used_memory = int(parts[3]) if parts[3] and parts[3] != "[Not Supported]" else 0

                # Map GPU bus_id to GPU data
                gpu = gpu_bus_id_to_gpu.get(gpu_bus_id)

                if gpu is not None:
                    users.append({
                        "gpu_id": gpu['index'],
                        "pid": pid,
                        "user": "process",  # nvidia-smi doesn't provide usernames directly
                        "command": process_name,
                        "memory_used_mib": used_memory,
                        "gpu_memory_total_mib": gpu['memory_total_mib']
                    })
            except (ValueError, IndexError):
                continue

    return {"gpus": gpus, "users": users}


def run_nvidia_smi_via_ssh(host_alias: str, timeout: int = 15) -> Dict[str, Any]:
    """
    Uses `ssh <host_alias> 'nvidia-smi --query-gpu=... --format=csv,noheader,nounits'`
    Returns a list of GPU dicts or raises RuntimeError on failure.
    """
    # The remote command - get GPU info and running processes
    remote_cmd = "nvidia-smi --query-gpu=index,name,pci.bus_id,utilization.gpu,memory.total,memory.used --format=csv,noheader,nounits && echo '---' && nvidia-smi --query-compute-apps=gpu_bus_id,pid,process_name,used_memory --format=csv,noheader,nounits"
    # ssh options:
    ssh_cmd = [
        "ssh",
        "-o", "BatchMode=yes",           # fail instead of prompting for password
        "-o", "ConnectTimeout=5",
        host_alias,
        remote_cmd
    ]
    try:
        completed = subprocess.run(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="ignore",
        )
    except subprocess.TimeoutExpired as ex:
        raise RuntimeError(f"ssh timeout: {ex}") from ex

    if completed.returncode != 0:
        # include stderr for debugging
        err = completed.stderr.strip()
        out = completed.stdout.strip()
        # if we got some output despite non-zero, try to continue; otherwise error
        if not out:
            raise RuntimeError(f"ssh returned code {completed.returncode}: {err}")
    else:
        err = completed.stderr.strip()
        out = completed.stdout.strip()

    # Parse the nvidia-smi output first
    result = parse_nvidia_smi_output(out)

    # Get usernames for the PIDs we found
    if result.get('users'):
        pids = [str(user['pid']) for user in result['users']]
        if pids:
            # Get usernames for all PIDs in one command
            ps_cmd = [
                "ssh",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=5",
                host_alias,
                f"ps -o pid,user --no-headers -p {','.join(pids)} 2>/dev/null || true"
            ]
            try:
                ps_completed = subprocess.run(
                    ps_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                    check=False,
                    encoding="utf-8",
                    errors="ignore",
                )

                # Parse ps output to create pid -> username mapping
                pid_to_user = {}
                if ps_completed.returncode == 0 and ps_completed.stdout.strip():
                    for line in ps_completed.stdout.strip().split('\n'):
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            pid_to_user[int(parts[0])] = parts[1]

                # Add usernames to the result
                for user in result['users']:
                    user['user'] = pid_to_user.get(user['pid'], 'unknown')

            except Exception:
                # If ps command fails, keep 'process' as username
                pass

    return result


async def poll_host_loop(host_alias: str):
    poll_interval = get_poll_interval()
    while True:
        try:
            loop = asyncio.get_running_loop()
            # run blocking ssh in the default threadpool
            result = await loop.run_in_executor(None, run_nvidia_smi_via_ssh, host_alias)
            latest[host_alias] = {"host_alias": host_alias, "timestamp": time.time(), **result}
        except Exception as e:
            latest[host_alias] = {"host_alias": host_alias, "timestamp": time.time(), "error": str(e)}
        await asyncio.sleep(poll_interval)


_override_hosts = None

@app.on_event("startup")
async def startup_pollers():
    hosts = get_hosts(_override_hosts)
    print("Polling SSH hosts:", hosts)
    for h in hosts:
        asyncio.create_task(poll_host_loop(h))


@app.get("/metrics")
async def get_metrics():
    return JSONResponse(list(latest.values()))


@app.get("/")
async def index():
    return RedirectResponse(url="/static/index.html")


def run_server(override_hosts=None):
    """Run the GPU monitor server."""
    global _override_hosts
    _override_hosts = override_hosts
    host = get_bind_host()
    port = get_bind_port()
    uvicorn.run(
        "gpu_monitor.monitor:app",
        host=host,
        port=port,
        log_level="info",
        access_log=False,   # <- suppress per-request logs
    )


if __name__ == "__main__":
    run_server()
