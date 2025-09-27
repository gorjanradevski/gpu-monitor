#!/usr/bin/env python3
"""
Minimal GPU monitor SSH'es into each host using the system ssh binary (so ProxyJump / IdentityFile are respected),
runs nvidia-smi, and serves a tiny web UI and JSON /metrics endpoint.
"""

import asyncio
import os
import subprocess
import time
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

SSH_CONFIG_PATH = os.path.expanduser(os.environ.get("SSH_CONFIG_PATH", "~/.ssh/config"))
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "5.0"))
BIND_HOST = os.environ.get("BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("BIND_PORT", "8000"))

app = FastAPI()
latest: Dict[str, Dict[str, Any]] = {}  # host_alias -> payload


def run_nvidia_smi_via_ssh(host_alias: str, timeout: int = 8) -> List[Dict[str, Any]]:
    """
    Uses `ssh <host_alias> 'nvidia-smi --query-gpu=... --format=csv,noheader,nounits'`
    Returns a list of GPU dicts or raises RuntimeError on failure.
    """
    # The remote command - use csv noheader nounits
    remote_cmd = "nvidia-smi --query-gpu=index,name,utilization.gpu,memory.total,memory.used --format=csv,noheader,nounits"
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

    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    gpus = []
    for ln in lines:
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) < 5:
            # sometimes names include commas; if so, try heuristic: index is first, last two are mems, one before last is util
            if len(parts) >= 4:
                # fallback parsing attempt
                try:
                    index = int(parts[0])
                    # not enough pieces to be confident, skip
                    continue
                except Exception:
                    continue
            continue
        if len(parts) > 5:
            try:
                index = int(parts[0])
                util = int(parts[-3])
                mem_total = int(parts[-2])
                mem_used = int(parts[-1])
                name = ", ".join(parts[1:-3])
            except Exception:
                continue
        else:
            try:
                index = int(parts[0])
                name = parts[1]
                util = int(parts[2])
                mem_total = int(parts[3])
                mem_used = int(parts[4])
            except Exception:
                continue
        gpus.append({
            "index": index,
            "name": name,
            "utilization_gpu": util,
            "memory_total_mib": mem_total,
            "memory_used_mib": mem_used,
        })
    return gpus


async def poll_host_loop(host_alias: str):
    while True:
        try:
            loop = asyncio.get_running_loop()
            # run blocking ssh in the default threadpool
            gpus = await loop.run_in_executor(None, run_nvidia_smi_via_ssh, host_alias)
            latest[host_alias] = {"host_alias": host_alias, "timestamp": time.time(), "gpus": gpus}
        except Exception as e:
            latest[host_alias] = {"host_alias": host_alias, "timestamp": time.time(), "error": str(e)}
        await asyncio.sleep(POLL_INTERVAL)


@app.on_event("startup")
async def startup_pollers():
    hosts = ["c535", "c536", "c104", "c314", "c328", "c324", "c606", "c610", "c602"]
    print("Polling SSH hosts:", hosts)
    for h in hosts:
        asyncio.create_task(poll_host_loop(h))


@app.get("/metrics")
async def get_metrics():
    return JSONResponse(list(latest.values()))


INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Minimal GPU Monitor</title>
<style>body{font-family:system-ui,Segoe UI,Roboto,Arial;padding:16px}table{border-collapse:collapse;width:100%;max-width:1200px}th,td{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f4f4f4}.high{background:#ffdddd}.med{background:#fff3cd}.small{font-size:0.9em;color:#666}</style>
</head><body>
<h2>Minimal GPU Monitor</h2>
<table id="tbl"><thead><tr><th>Host</th><th>GPU</th><th>Name</th><th>GPU %</th><th>Mem used / total (MiB)</th></tr></thead><tbody id="body"></tbody></table>
<script>
async function fetchAndRender(){
  try{
    const r = await fetch('/metrics');
    const data = await r.json();
    const tbody = document.getElementById('body');
    tbody.innerHTML = '';
    data.forEach(h=>{
      if(h.error){
        const tr = document.createElement('tr');
        tr.innerHTML = `<td colspan="5"><strong>${h.host_alias}</strong> — error: ${h.error}</td>`;
        tbody.appendChild(tr);
        return;
      }
      (h.gpus||[]).forEach(g=>{
        const tr = document.createElement('tr');
        const util = g.utilization_gpu||0;
        if(util>=90) tr.className='high';
        else if(util>=60) tr.className='med';
        tr.innerHTML = `<td>${h.host_alias}</td>
                        <td>${g.index}</td>
                        <td>${g.name}</td>
                        <td>${util}%</td>
                        <td>${g.memory_used_mib} / ${g.memory_total_mib}</td>`;
        tbody.appendChild(tr);
      });
    });
  }catch(e){
    console.error(e);
  }
}
fetchAndRender();
setInterval(fetchAndRender, 2000);
</script>
</body></html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(INDEX_HTML)


if __name__ == "__main__":
    uvicorn.run("server:app", host=BIND_HOST, port=BIND_PORT, log_level="info")
