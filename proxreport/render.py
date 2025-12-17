from __future__ import annotations

from datetime import datetime, timezone
import html
from typing import Dict, Optional

from .config import AppConfig, CapacityProfile
from .metrics import HostSnapshot


def render_dashboard(cfg: AppConfig, snap: HostSnapshot) -> str:
    thresholds = cfg.thresholds

    cpu_pct = snap.cpu_usage_percent
    cpu_state = _state_for_percent(cpu_pct, thresholds.cpu_warn, thresholds.cpu_crit)

    mem_used_pct = None
    mem_used_str = "n/a"
    if snap.mem_total_kb and snap.mem_available_kb is not None:
        used_kb = max(0, snap.mem_total_kb - snap.mem_available_kb)
        mem_used_pct = (used_kb / snap.mem_total_kb) * 100.0 if snap.mem_total_kb else None
        mem_used_str = f"{_kb_to_gib(used_kb):.1f} / {_kb_to_gib(snap.mem_total_kb):.1f} GiB"

    ram_state = _state_for_percent(mem_used_pct, thresholds.ram_warn, thresholds.ram_crit)

    capacity = estimate_capacity(cfg, snap)

    updated = datetime.fromtimestamp(snap.now_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    disk_rows = []
    for d in snap.disks:
        pct = (d.used_bytes / d.total_bytes) * 100.0 if d.total_bytes else None
        state = _state_for_percent(pct, thresholds.disk_warn, thresholds.disk_crit)
        disk_rows.append(
            {
                "mount": d.mountpoint,
                "pct": pct,
                "state": state,
                "value": f"{_bytes_to_gib(d.used_bytes):.1f} / {_bytes_to_gib(d.total_bytes):.1f} GiB",
            }
        )

    load_str = "n/a"
    if snap.load1 is not None:
        load_str = f"{snap.load1:.2f} {snap.load5:.2f} {snap.load15:.2f} (1/5/15m)"

    uptime_str = "n/a"
    if snap.uptime_seconds is not None:
        uptime_str = _format_duration(int(snap.uptime_seconds))

    auto = max(1, int(cfg.server.autorefresh_seconds))

    # No JS: refresh via meta tag.
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <meta http-equiv=\"refresh\" content=\"{auto}\">
  <title>ProxReport - {html.escape(snap.hostname)}</title>
  <link rel=\"stylesheet\" href=\"/static/style.css\">
</head>
<body>
  <div class=\"container\">
    <div class=\"header\">
      <div>
        <h1>ProxReport — {html.escape(snap.hostname)}</h1>
        <div class=\"small\">Updated {html.escape(updated)} · Auto-refresh {auto}s · Uptime {html.escape(uptime_str)}</div>
      </div>
      <div class=\"small\">Load: <code>{html.escape(load_str)}</code> · CPUs: <code>{snap.cpu_count}</code></div>
    </div>

    <div class=\"grid\">
      <div class=\"card\">
        <div class=\"row\">
          <div class=\"label\">CPU usage</div>
          {bar(cpu_pct, cpu_state)}
          <div class=\"value\"><span class=\"{cpu_state}\">{_pct_str(cpu_pct)}</span></div>
        </div>
        <div class=\"row\">
          <div class=\"label\">RAM usage</div>
          {bar(mem_used_pct, ram_state)}
          <div class=\"value\"><span class=\"{ram_state}\">{_pct_str(mem_used_pct)}</span> · {html.escape(mem_used_str)}</div>
        </div>
        {''.join(_disk_row(r) for r in disk_rows)}
      </div>

      <div class=\"card\">
        <div class=\"label\">Capacity estimate (conservative)</div>
        <div class=\"small\">Based on current load + available RAM/disk. Tunable in config.</div>
        <table>
          <thead><tr><th>Profile</th><th>vCPU</th><th>RAM</th><th>Disk</th><th>Estimated VMs</th></tr></thead>
          <tbody>
            {_capacity_row(capacity['standard'])}
            {_capacity_row(capacity['light'])}
          </tbody>
        </table>
      </div>

      <div class=\"card\">
        <div class=\"label\">Config</div>
        <div class=\"kv small\">
          <div>Mountpoints</div><div><code>{html.escape(', '.join(cfg.mountpoints))}</code></div>
          <div>Reserves</div><div><code>{cfg.capacity.reserve_cores} cores, {cfg.capacity.reserve_ram_mb} MiB RAM, {cfg.capacity.reserve_disk_gb} GiB disk</code></div>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""


def _disk_row(row: Dict[str, object]) -> str:
    pct = row["pct"]
    state = row["state"]
    mount = html.escape(str(row["mount"]))
    val = html.escape(str(row["value"]))
    return f"""<div class=\"row\">
      <div class=\"label\">Disk {mount}</div>
      {bar(pct, state)}
      <div class=\"value\"><span class=\"{state}\">{_pct_str(pct)}</span> · {val}</div>
    </div>"""


def bar(percent: Optional[float], state_class: str) -> str:
    pct = 0.0 if percent is None else max(0.0, min(100.0, float(percent)))
    return f"<div class=\"bar\"><div class=\"fill {state_class}\" style=\"width:{pct:.1f}%;\"></div></div>"


def _pct_str(p: Optional[float]) -> str:
    return "n/a" if p is None else f"{p:.1f}%"


def _state_for_percent(p: Optional[float], warn: int, crit: int) -> str:
    if p is None:
        return "state-amber"
    if p >= crit:
        return "state-red"
    if p >= warn:
        return "state-amber"
    return "state-green"


def _kb_to_gib(kb: int) -> float:
    return (kb * 1024) / (1024 ** 3)


def _bytes_to_gib(b: int) -> float:
    return b / (1024 ** 3)


def _format_duration(seconds: int) -> str:
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {mins}m"
    if hours:
        return f"{hours}h {mins}m"
    if mins:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def estimate_capacity(cfg: AppConfig, snap: HostSnapshot) -> Dict[str, Dict[str, object]]:
    # CPU: approximate "available" cores as (cores - 1m load - reserve).
    # This intentionally stays simple and conservative.
    load1 = snap.load1 or 0.0
    avail_cores = max(0.0, float(snap.cpu_count) - float(load1) - float(cfg.capacity.reserve_cores))

    # RAM: based on MemAvailable.
    avail_ram_mb = None
    if snap.mem_available_kb is not None:
        avail_ram_mb = max(0.0, (snap.mem_available_kb / 1024.0) - float(cfg.capacity.reserve_ram_mb))

    # Disk: pick the tightest (lowest free) across monitored mountpoints.
    avail_disk_gb = None
    if snap.disks:
        free_gb = min((_bytes_to_gib(d.free_bytes) for d in snap.disks), default=None)
        if free_gb is not None:
            avail_disk_gb = max(0.0, free_gb - float(cfg.capacity.reserve_disk_gb))

    def calc(profile: CapacityProfile) -> Dict[str, object]:
        cpu_limit = int(avail_cores // max(1, profile.vcpus))
        ram_limit = cpu_limit
        disk_limit = cpu_limit

        if avail_ram_mb is not None:
            ram_limit = int(avail_ram_mb // max(1, profile.ram_mb))

        if avail_disk_gb is not None:
            disk_limit = int(avail_disk_gb // max(1, profile.disk_gb))

        est = max(0, min(cpu_limit, ram_limit, disk_limit))

        return {
            "name": profile.name,
            "vcpus": profile.vcpus,
            "ram_mb": profile.ram_mb,
            "disk_gb": profile.disk_gb,
            "est": est,
        }

    return {
        "standard": calc(cfg.capacity.standard),
        "light": calc(cfg.capacity.light),
    }


def _capacity_row(row: Dict[str, object]) -> str:
    name = html.escape(str(row["name"]))
    vcpus = int(row["vcpus"])
    ram_mb = int(row["ram_mb"])
    disk_gb = int(row["disk_gb"])
    est = int(row["est"])
    return f"<tr><td>{name}</td><td>{vcpus}</td><td>{ram_mb} MiB</td><td>{disk_gb} GiB</td><td><code>{est}</code></td></tr>"

def render_cluster_dashboard(nodes: list[dict]) -> str:
    """
    nodes: lista de dicts con:
      - name
      - cpu_pct
      - cpu_state
      - ram_pct
      - ram_state
      - disk_pct
      - disk_state
      - est_vms
    """

    cards_html = []

    for n in nodes:
        cards_html.append(f"""
        <div class="node-card {n['cpu_state']}">
          <a href="/node/{html.escape(n['name'])}">
            <h2>{html.escape(n['name'])}</h2>

            {_compact_row("CPU", n['cpu_pct'], n['cpu_state'])}
            {_compact_row("RAM", n['ram_pct'], n['ram_state'])}
            {_compact_row("Disk", n['disk_pct'], n['disk_state'])}

            <div class="small" style="margin-top:6px;">
              Est. VMs: <code>{n['est_vms']}</code>
            </div>
          </a>
        </div>
        """)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ProxReport - Cluster</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>ProxReport — Cluster overview</h1>
      <div class="small">{len(nodes)} nodes</div>
    </div>

    <div class="grid grid-nodes">
      {''.join(cards_html)}
    </div>
  </div>
</body>
</html>
"""

def _compact_row(label: str, pct: float | None, state: str) -> str:
    pct_val = 0 if pct is None else max(0, min(100, pct))
    pct_str = "n/a" if pct is None else f"{pct_val:.1f}%"

    return f"""
    <div class="row compact">
      <div class="label">{label}</div>
      <div class="bar">
        <div class="fill {state}" style="width:{pct_val:.1f}%;"></div>
      </div>
      <div class="value {state}">{pct_str}</div>
    </div>
    """
