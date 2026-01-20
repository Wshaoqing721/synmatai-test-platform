import json
import math
from datetime import datetime
from pathlib import Path


def ts_to_str(ts: float | int | None) -> str:
        if ts is None:
                return "-"
        try:
                return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
                return "-"


def round_s(v: float | int | None, ndigits: int = 3):
        if v is None:
                return None
        try:
                return round(float(v), ndigits)
        except Exception:
                return None


def _percentile(values: list[float], p: float) -> float | None:
        if not values:
                return None
        values = sorted(values)
        if p <= 0:
                return values[0]
        if p >= 100:
                return values[-1]
        k = (len(values) - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
                return values[int(k)]
        return values[f] * (c - k) + values[c] * (k - f)


def _pick_step(n: int, target_points: int = 240) -> int:
        if n <= 0:
                return 1
        return max(1, int(math.ceil(n / max(1, target_points))))


def _status_is_success(status: str | None, success_field: bool | None = None) -> bool | None:
        if isinstance(success_field, bool):
                return success_field
        if status is None:
                return None
        s = str(status).lower()
        if s in {"done", "finished", "success", "succeeded", "completed", "complete"}:
                return True
        if s in {"failed", "error", "cancelled", "canceled"}:
                return False
        return None


class ReportWriter:
        def __init__(self, ws_monitor=None, task_manager=None, sys_monitor=None):
                self.ws_monitor = ws_monitor
                self.task_manager = task_manager
                self.sys_monitor = sys_monitor

        # ---------- Task 维度 ----------
        def build_task_table(self, tasks: dict) -> list[dict]:
                rows: list[dict] = []
                ws_base_ts = getattr(self.ws_monitor, "start_ts", None)

                for tid, t in (tasks or {}).items():
                        submit_ts = t.get("submit_ts")
                        start_ts = t.get("start_ts")
                        finish_ts = t.get("finish_ts")

                        # WebSocketTaskMonitor: try to infer absolute timestamps from status_timeline (relative seconds)
                        if (start_ts is None or finish_ts is None) and isinstance(t.get("status_timeline"), list) and ws_base_ts:
                                timeline = t.get("status_timeline") or []

                                def is_running(x: dict) -> bool:
                                        s = (x.get("status") or "").lower()
                                        return s in {"running", "run", "in_progress", "in-progress", "processing"}

                                def is_terminal(x: dict) -> bool:
                                        s = (x.get("status") or "").lower()
                                        return s in {"done", "completed", "complete", "success", "succeeded", "failed", "error", "cancelled", "canceled", "finish", "finished"}

                                running = next((x for x in timeline if is_running(x)), None)
                                terminal = next((x for x in reversed(timeline) if is_terminal(x)), None)

                                if start_ts is None and running and running.get("ts") is not None:
                                        start_ts = float(ws_base_ts) + float(running.get("ts"))
                                if finish_ts is None and terminal and terminal.get("ts") is not None:
                                        finish_ts = float(ws_base_ts) + float(terminal.get("ts"))

                        queue_time = None
                        if submit_ts is not None and start_ts is not None:
                                queue_time = float(start_ts) - float(submit_ts)

                        duration = t.get("duration")
                        if duration is None and start_ts is not None and finish_ts is not None:
                                duration = float(finish_ts) - float(start_ts)

                        status = t.get("status")
                        success = _status_is_success(status, t.get("success"))

                        payload = t.get("payload")
                        # prefer final status payload as "result"; fallback to submit response
                        result_obj = t.get("final") if t.get("final") is not None else t.get("submit_resp")

                        rows.append({
                                "task_id": t.get("task_id") or tid,
                                "task_type": t.get("task_type"),
                                "status": status,
                                "success": success,
                                "queue_time_s": round_s(queue_time, 3),
                                "duration_s": round_s(duration, 3),
                                "submit_ts": submit_ts,
                                "start_ts": start_ts,
                                "finish_ts": finish_ts,
                                "submit_time": ts_to_str(submit_ts),
                                "start_time": ts_to_str(start_ts),
                                "finish_time": ts_to_str(finish_ts),
                                "payload": payload,
                                "result": result_obj,
                        })

                rows.sort(key=lambda r: (r.get("submit_ts") is None, r.get("submit_ts") or 0, str(r.get("task_id") or "")))
                return rows

        def build_task_summary(self, table: list[dict]) -> dict:
                total = len(table)
                success_tasks = sum(1 for t in table if t.get("success") is True)
                failed_tasks = sum(1 for t in table if t.get("success") is False)

                durations = [float(t["duration_s"]) for t in table if t.get("duration_s") is not None]
                queues = [float(t["queue_time_s"]) for t in table if t.get("queue_time_s") is not None]

                return {
                        "total_tasks": total,
                        "success_tasks": success_tasks,
                        "failed_tasks": failed_tasks,
                        "success_rate_pct": round_s((success_tasks / total * 100.0) if total else 0.0, 2),
                        "avg_duration_s": round_s((sum(durations) / len(durations)) if durations else None, 3),
                        "p50_duration_s": round_s(_percentile(durations, 50) if durations else None, 3),
                        "p95_duration_s": round_s(_percentile(durations, 95) if durations else None, 3),
                        "avg_queue_time_s": round_s((sum(queues) / len(queues)) if queues else None, 3),
                        "p95_queue_time_s": round_s(_percentile(queues, 95) if queues else None, 3),
                }

        # ---------- System 维度 ----------
        def summarize_system_metrics(self, records: list[dict]) -> dict | None:
                if not records:
                        return None

                gpu_available = None
                gpu_reason = None
                first = records[0] if records else None
                if isinstance(first, dict):
                        gpu_available = first.get("gpu_available")
                        gpu_reason = first.get("gpu_reason")
                if gpu_available is None:
                        # heuristic fallback
                        any_gpu = any(m.get("gpu") is not None for m in records if isinstance(m, dict))
                        any_gpu_mem = any(m.get("gpu_mem") is not None for m in records if isinstance(m, dict))
                        gpu_available = bool(any_gpu or any_gpu_mem)
                        gpu_reason = None if gpu_available else "GPU metrics unavailable"

                def stats(vals: list[float | int | None]):
                        vv = [float(x) for x in vals if x is not None]
                        if not vv:
                                return None
                        return {
                                "avg": round_s(sum(vv) / len(vv), 2),
                                "min": round_s(min(vv), 2),
                                "max": round_s(max(vv), 2),
                        }

                cpu = [m.get("cpu") for m in records]
                mem = [m.get("mem") for m in records]
                gpu = [m.get("gpu") for m in records]
                gpu_mem = [m.get("gpu_mem") for m in records]

                base_ts = records[0].get("ts")
                step = _pick_step(len(records), target_points=240)
                timeline = []
                for i, m in enumerate(records):
                        if i % step != 0:
                                continue
                        ts = m.get("ts")
                        rel = (float(ts) - float(base_ts)) if (ts is not None and base_ts is not None) else None
                        timeline.append({
                                "t_s": round_s(rel, 1),
                                "cpu_pct": m.get("cpu"),
                                "mem_pct": m.get("mem"),
                                "gpu_pct": m.get("gpu"),
                                "gpu_mem_mb": m.get("gpu_mem"),
                        })

                return {
                        "gpu_available": gpu_available,
                        "gpu_reason": gpu_reason,
                        "units": {
                                "t_s": "s",
                                "cpu_pct": "%",
                                "mem_pct": "%",
                                "gpu_pct": "%",
                                "gpu_mem_mb": "MB",
                        },
                        "summary": {
                                "cpu_pct": stats(cpu),
                                "mem_pct": stats(mem),
                                "gpu_pct": stats(gpu),
                                "gpu_mem_mb": stats(gpu_mem),
                        },
                        "timeline": timeline,
                }

        # ---------- 主入口 ----------
        def write(self, path):
                path = Path(path)
                html_path = path.with_suffix(".html")

                # ---------- tasks ----------
                if self.ws_monitor is not None:
                        tasks = self.ws_monitor.tasks
                        task_summary_legacy = None
                elif self.task_manager is not None:
                        tasks = self.task_manager.export_tasks()
                        task_summary_legacy = self.task_manager.summary()
                else:
                        tasks = {}
                        task_summary_legacy = None

                task_table = self.build_task_table(tasks)
                task_summary_v2 = self.build_task_summary(task_table)

                # ---------- system metrics (raw) ----------
                system_metrics = []
                if self.sys_monitor:
                        raw = getattr(self.sys_monitor, "records", None) or getattr(self.sys_monitor, "metrics", [])
                        for m in (raw or []):
                                system_metrics.append({
                                        "ts": m.get("ts"),
                                        "cpu": m.get("cpu"),
                                        "mem": m.get("mem"),          # percent
                                        "gpu": m.get("gpu"),          # util %
                                        "gpu_mem": m.get("gpu_mem"),  # MB
                                        "gpu_available": m.get("gpu_available"),
                                        "gpu_reason": m.get("gpu_reason"),
                                })

                system_metrics_v2 = self.summarize_system_metrics(system_metrics)

                report = {
                        "meta": {
                                "generated_at": ts_to_str(datetime.now().timestamp()),
                                "schema_version": 2,
                        },
                        # legacy keys (keep)
                        "tasks": tasks,
                        "task_summary": task_summary_legacy,
                        "system_metrics": system_metrics,
                        # v2 keys (new)
                        "task_table": task_table,
                        "task_summary_v2": task_summary_v2,
                        "system_metrics_v2": system_metrics_v2,
                }

                path.parent.mkdir(parents=True, exist_ok=True)

                with open(path, "w", encoding="utf-8") as f:
                        json.dump(report, f, indent=2, ensure_ascii=False)

                with open(html_path, "w", encoding="utf-8") as f:
                        f.write(self._render_html(report))

                print(f"✅ Report generated: {path}")
                print(f"🌐 HTML report: {html_path}")

                return str(path)

        # ---------- Ramp 报告 ----------
        def write_ramp_report(self, path, ramp_report: dict):
                """写入爬坡测试报告（JSON + HTML）。"""
                path = Path(path)
                html_path = path.with_suffix(".html")

                ramp_results = list((ramp_report or {}).get("ramp_results") or [])
                enriched_results: list[dict] = []

                for r in ramp_results:
                        tasks = r.get("tasks") or {}
                        task_table = self.build_task_table(tasks) if isinstance(tasks, dict) else []
                        task_summary_v2 = self.build_task_summary(task_table)

                        system_metrics = r.get("system_metrics") or []
                        system_metrics_v2 = self.summarize_system_metrics(system_metrics) if isinstance(system_metrics, list) else None

                        enriched = dict(r)
                        enriched["task_table"] = task_table
                        enriched["task_summary_v2"] = task_summary_v2
                        enriched["system_metrics_v2"] = system_metrics_v2
                        enriched_results.append(enriched)

                report = {
                        "meta": {
                                "generated_at": ts_to_str(datetime.now().timestamp()),
                                "schema_version": 2,
                                "report_type": "ramp",
                        },
                        "ramp": {
                                "max_stable_concurrency": (ramp_report or {}).get("max_stable_concurrency", 0),
                                "ramp_results": enriched_results,
                        },
                }

                path.parent.mkdir(parents=True, exist_ok=True)

                with open(path, "w", encoding="utf-8") as f:
                        json.dump(report, f, indent=2, ensure_ascii=False)

                with open(html_path, "w", encoding="utf-8") as f:
                        f.write(self._render_ramp_html(report))

                print(f"✅ Ramp report generated: {path}")
                print(f"🌐 Ramp HTML report: {html_path}")

                return str(path)

        def _render_ramp_html(self, report: dict) -> str:
                report_json = json.dumps(report, ensure_ascii=False)

                # 不用 Python f-string：避免 JS 里的大括号/模板字符串和 f-string 冲突
                return (
                        """<!DOCTYPE html>
<html lang=\"zh\">
<head>
  <meta charset=\"utf-8\"/>
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>
  <title>Nexus Ramp Test Report</title>
  <script src=\"https://cdn.jsdelivr.net/npm/echarts@5\"></script>
  <style>
    body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial;margin:0;background:#0b1220;color:rgba(255,255,255,0.92)}
    .container{max-width:1200px;margin:0 auto;padding:24px 18px 40px}
    .card{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);border-radius:14px;padding:14px;margin-top:12px}
    .title{font-size:22px;font-weight:700}
    .subtitle{color:rgba(255,255,255,0.70);font-size:13px;margin-top:6px}
    .chart{height:380px}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th,td{padding:10px;border-bottom:1px solid rgba(255,255,255,0.10);white-space:nowrap;text-align:left}
    th{background:rgba(255,255,255,0.05)}
    .badge{display:inline-flex;align-items:center;gap:6px;padding:2px 8px;border-radius:999px;border:1px solid rgba(255,255,255,0.12);background:rgba(255,255,255,0.06)}
    .dot{width:8px;height:8px;border-radius:50%}
    .dot.good{background:#3ddc97}
    .dot.bad{background:#ff5d5d}
  </style>
</head>
<body>
  <div class=\"container\">
    <div class=\"title\">Nexus 爬坡压测报告</div>
    <div class=\"subtitle\">Generated at: <span id=\"generatedAt\">-</span></div>

    <div class=\"card\">
      <div class=\"subtitle\">最大稳定并发: <b id=\"maxStable\">-</b> · 档位数: <b id=\"steps\">-</b></div>
    </div>

    <div class=\"card\">
      <h3 style=\"margin:0 0 10px\">曲线</h3>
      <div id=\"rampChart\" class=\"chart\"></div>
    </div>

    <div class=\"card\">
      <h3 style=\"margin:0 0 10px\">档位明细</h3>
      <div style=\"overflow-x:auto\">
        <table>
          <thead>
            <tr>
              <th>Concurrency</th><th>Stable</th><th>Reason</th><th>Tasks</th><th>Failure Rate</th><th>Avg Duration(s)</th><th>Avg Queue(s)</th>
            </tr>
          </thead>
          <tbody id=\"rampTable\"></tbody>
        </table>
      </div>
      <div class=\"subtitle\">JSON 内包含每档位 task_table、task_summary_v2、system_metrics_v2</div>
    </div>
  </div>

  <script type=\"application/json\" id=\"reportData\">"""
                        + report_json +
                        """</script>
  <script>
    const report = JSON.parse(document.getElementById('reportData').textContent);
    const meta = report.meta || {};
    const ramp = report.ramp || {};
    const results = ramp.ramp_results || [];

    document.getElementById('generatedAt').textContent = meta.generated_at || '-';
    document.getElementById('maxStable').textContent = String(ramp.max_stable_concurrency ?? '-');
    document.getElementById('steps').textContent = String(results.length);

    function fmtPct(x){
      if(x===null||x===undefined) return '-';
      const v = Number(x);
      if(Number.isNaN(v)) return '-';
      return (v*100).toFixed(2)+'%';
    }
    function fmtNum(x){
      if(x===null||x===undefined) return '-';
      const v = Number(x);
      if(Number.isNaN(v)) return '-';
      return v.toFixed(3);
    }

    const tbody = document.getElementById('rampTable');
    tbody.innerHTML = '';
    for(const r of results){
      const tr = document.createElement('tr');
      const dot = r.stable ? 'good' : 'bad';
      const badge = document.createElement('span');
      badge.className = 'badge';
      const dotEl = document.createElement('span');
      dotEl.className = 'dot ' + dot;
      badge.appendChild(dotEl);
      const txt = document.createElement('span');
      txt.textContent = r.stable ? 'STABLE' : 'UNSTABLE';
      badge.appendChild(txt);

      const metrics = r.metrics || {};
      const tasks = r.task_summary_v2 || {};

      const cells = [
        String(r.concurrency ?? '-'),
        badge,
        String(r.reason ?? '-'),
        String(tasks.total_tasks ?? metrics.task_count ?? '-'),
        fmtPct(metrics.failure_rate),
        fmtNum(metrics.avg_duration),
        fmtNum(metrics.avg_queue_time),
      ];

      for(const c of cells){
        const td = document.createElement('td');
        if(c instanceof HTMLElement) td.appendChild(c);
        else td.textContent = c;
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }

    const xs = results.map(r => r.concurrency ?? 0);
    const avgDur = results.map(r => (r.metrics && r.metrics.avg_duration) ?? null);
    const avgQueue = results.map(r => (r.metrics && r.metrics.avg_queue_time) ?? null);
    const failRate = results.map(r => (r.metrics && r.metrics.failure_rate) ?? null);

    const chart = echarts.init(document.getElementById('rampChart'));
    chart.setOption({
      tooltip: {trigger:'axis'},
      legend: {},
      grid: {left:50,right:30,top:40,bottom:40},
      xAxis: {type:'category',data:xs},
      yAxis: [
        {type:'value',name:'Seconds'},
        {type:'value',name:'Failure Rate',min:0,max:1,axisLabel:{formatter:(v)=> (v*100).toFixed(0)+'%'}}
      ],
      series: [
        {name:'Avg Duration (s)',type:'line',data:avgDur,smooth:true,symbolSize:6},
        {name:'Avg Queue (s)',type:'line',data:avgQueue,smooth:true,symbolSize:6},
        {name:'Failure Rate',type:'line',yAxisIndex:1,data:failRate,smooth:true,symbolSize:6},
      ]
    });
    window.addEventListener('resize', ()=> chart.resize());
  </script>
</body>
</html>"""
                )

        # ---------- HTML ----------
        def _render_html(self, report: dict) -> str:
                report_json = json.dumps(report, ensure_ascii=False)

                return f"""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Nexus Load Test Report</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5"></script>
    <style>
        :root {{
            --bg: #0b1220;
            --panel: rgba(255,255,255,0.06);
            --panel2: rgba(255,255,255,0.09);
            --text: rgba(255,255,255,0.92);
            --muted: rgba(255,255,255,0.70);
            --border: rgba(255,255,255,0.12);
            --good: #3ddc97;
            --bad: #ff5d5d;
            --warn: #ffcc66;
            --brand: #7aa2ff;
        }}

        body {{
            font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
            margin: 0;
            background: radial-gradient(1200px 600px at 30% -20%, rgba(122,162,255,0.35), transparent 60%),
                                    radial-gradient(900px 500px at 90% 10%, rgba(61,220,151,0.25), transparent 60%),
                                    var(--bg);
            color: var(--text);
        }}

        .container {{ max-width: 1200px; margin: 0 auto; padding: 24px 18px 40px; }}
        .header {{ display:flex; justify-content: space-between; align-items: end; gap: 12px; flex-wrap: wrap; }}
        .title {{ font-size: 22px; font-weight: 700; letter-spacing: 0.3px; }}
        .subtitle {{ color: var(--muted); font-size: 13px; }}

        .grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; margin-top: 14px; }}

        .card {{
            grid-column: span 12;
            background: linear-gradient(180deg, var(--panel), transparent 120%);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 14px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.25);
        }}

        .card h2 {{ margin: 0 0 10px; font-size: 16px; }}

        .kpis {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 10px; }}
        .kpi {{ grid-column: span 3; background: var(--panel2); border: 1px solid var(--border); border-radius: 12px; padding: 10px; }}
        .kpi .label {{ color: var(--muted); font-size: 12px; }}
        .kpi .value {{ font-size: 18px; font-weight: 700; margin-top: 4px; }}
        .kpi .hint {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}

        .chart {{ height: 380px; }}

        .toolbar {{ display:flex; align-items:center; justify-content: space-between; gap: 10px; margin: 8px 0 10px; flex-wrap: wrap; }}
        .search {{
            display:flex; align-items:center; gap: 8px;
            background: rgba(255,255,255,0.06);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 8px 10px;
            min-width: 260px;
        }}
        .search input {{ width: 100%; background: transparent; border: none; outline: none; color: var(--text); font-size: 13px; }}
        .btn {{ cursor:pointer; user-select:none; background: rgba(255,255,255,0.06); border: 1px solid var(--border); color: var(--text); border-radius: 12px; padding: 8px 10px; font-size: 13px; }}
        .btn:hover {{ border-color: rgba(122,162,255,0.55); }}
        .muted {{ color: var(--muted); }}

        .table-wrap {{ overflow-x: auto; border-radius: 12px; border: 1px solid var(--border); }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th, td {{ padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.08); white-space: nowrap; }}
        th {{ text-align: left; color: rgba(255,255,255,0.86); background: rgba(255,255,255,0.05); position: sticky; top: 0; }}
        tr:hover td {{ background: rgba(122,162,255,0.07); }}

        .badge {{ display:inline-flex; align-items:center; gap:6px; padding:2px 8px; border-radius: 999px; font-size: 12px; border: 1px solid var(--border); background: rgba(255,255,255,0.06); }}
        .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }}
        .dot.good {{ background: var(--good); }}
        .dot.bad {{ background: var(--bad); }}

        @media (max-width: 920px) {{
            .kpi {{ grid-column: span 6; }}
        }}
    </style>
</head>

<body>
    <div class="container">
        <div class="header">
            <div>
                <div class="title">Nexus 压测报告</div>
                <div class="subtitle">Generated at: <span id="generatedAt"></span> · Schema v<span id="schemaVer"></span></div>
            </div>
            <div class="subtitle">任务表支持搜索 / 排序，图表已做降采样优化</div>
        </div>

        <div class="grid">
            <div class="card">
                <h2>任务总览</h2>
                <div class="kpis">
                    <div class="kpi"><div class="label">总任务</div><div class="value" id="k_total">-</div><div class="hint muted">tasks</div></div>
                    <div class="kpi"><div class="label">成功</div><div class="value" id="k_success">-</div><div class="hint muted">success</div></div>
                    <div class="kpi"><div class="label">失败</div><div class="value" id="k_fail">-</div><div class="hint muted">failed</div></div>
                    <div class="kpi"><div class="label">成功率</div><div class="value" id="k_rate">-</div><div class="hint muted">%</div></div>
                    <div class="kpi"><div class="label">平均执行</div><div class="value" id="k_avg_dur">-</div><div class="hint muted">duration</div></div>
                    <div class="kpi"><div class="label">P95 执行</div><div class="value" id="k_p95_dur">-</div><div class="hint muted">duration</div></div>
                    <div class="kpi"><div class="label">平均排队</div><div class="value" id="k_avg_q">-</div><div class="hint muted">queue</div></div>
                    <div class="kpi"><div class="label">P95 排队</div><div class="value" id="k_p95_q">-</div><div class="hint muted">queue</div></div>
                </div>
            </div>

            <div class="card">
                <h2>任务明细</h2>
                <div class="toolbar">
                    <div class="search"><span class="muted">🔎</span><input id="taskSearch" placeholder="搜索 task_id / type / status" /></div>
                    <div style="display:flex; gap:8px; flex-wrap:wrap;">
                        <div class="btn" id="btnSortDur">按执行时长排序</div>
                        <div class="btn" id="btnSortQueue">按排队时长排序</div>
                        <div class="btn" id="btnReset">重置</div>
                    </div>
                </div>

                <div class="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>类型</th>
                                <th>状态</th>
                                <th>成功</th>
                                <th>排队(s)</th>
                                <th>执行(s)</th>
                                <th>提交时间</th>
                                <th>开始时间</th>
                                <th>结束时间</th>
                                                                <th>Payload</th>
                                                                <th>Result</th>
                            </tr>
                        </thead>
                        <tbody id="taskTable"></tbody>
                    </table>
                </div>
                <div class="subtitle" style="margin-top:8px;">排队 = submit → start；执行 = start → finish</div>
            </div>

            <div class="card">
                <h2>任务耗时对比</h2>
                <div id="taskChart" class="chart"></div>
            </div>

            <div class="card">
                <h2>系统资源使用情况</h2>
                <div id="sysChart" class="chart"></div>
                <div class="subtitle" id="sysSummary" style="margin-top:8px;"></div>
            </div>
        </div>
    </div>

    <script type="application/json" id="reportData">{report_json}</script>
    <script>
        const report = JSON.parse(document.getElementById('reportData').textContent);

        function fmtNumber(v, digits=2) {{
            if (v === null || v === undefined || Number.isNaN(v)) return "-";
            const n = Number(v);
            if (!Number.isFinite(n)) return "-";
            return n.toFixed(digits);
        }}

        function fmtSeconds(v) {{
            if (v === null || v === undefined || Number.isNaN(v)) return "-";
            const s = Number(v);
            if (!Number.isFinite(s)) return "-";
            if (s < 1) return `${{Math.round(s*1000)}} ms`;
            if (s < 60) return `${{fmtNumber(s, 2)}} s`;
            const m = Math.floor(s / 60);
            const r = s - m*60;
            return `${{m}}m ${{fmtNumber(r, 1)}}s`;
        }}

        document.getElementById('generatedAt').textContent = (report.meta && report.meta.generated_at) ? report.meta.generated_at : '-';
        document.getElementById('schemaVer').textContent = (report.meta && report.meta.schema_version) ? report.meta.schema_version : '-';

        // KPIs
        const k = report.task_summary_v2 || {{}};
        document.getElementById('k_total').textContent = k.total_tasks ?? '-';
        document.getElementById('k_success').textContent = k.success_tasks ?? '-';
        document.getElementById('k_fail').textContent = k.failed_tasks ?? '-';
        document.getElementById('k_rate').textContent = (k.success_rate_pct !== null && k.success_rate_pct !== undefined) ? fmtNumber(k.success_rate_pct, 2) : '-';
        document.getElementById('k_avg_dur').textContent = fmtSeconds(k.avg_duration_s);
        document.getElementById('k_p95_dur').textContent = fmtSeconds(k.p95_duration_s);
        document.getElementById('k_avg_q').textContent = fmtSeconds(k.avg_queue_time_s);
        document.getElementById('k_p95_q').textContent = fmtSeconds(k.p95_queue_time_s);

        // Task table
        let tableRows = Array.isArray(report.task_table) ? report.task_table.slice() : [];
        const originalRows = tableRows.slice();

        function renderTable(rows) {{
            const tbody = document.getElementById('taskTable');
            tbody.innerHTML = '';

                        function escapeHtml(s) {{
                                return String(s)
                                        .replaceAll('&', '&amp;')
                                        .replaceAll('<', '&lt;')
                                        .replaceAll('>', '&gt;')
                                        .replaceAll('"', '&quot;')
                                        .replaceAll("'", '&#39;');
                        }}

                        function jsonCell(obj) {{
                                if (obj === null || obj === undefined) return '-';
                                let txt = '';
                                try {{
                                        txt = (typeof obj === 'string') ? obj : JSON.stringify(obj, null, 2);
                                }} catch (e) {{
                                        txt = String(obj);
                                }}
                                const safe = escapeHtml(txt);
                                const preview = escapeHtml(txt.length > 80 ? (txt.slice(0, 80) + '…') : txt);
                                return `<details><summary class=\"muted\">${{preview}}</summary><pre style=\"white-space:pre-wrap;max-width:900px;\">${{safe}}</pre></details>`;
                        }}

            for (const t of rows) {{
                let dotClass = '';
                let label = String(t.status ?? '-');
                if (t.success === true) dotClass = 'good';
                else if (t.success === false) dotClass = 'bad';
                const badge = `<span class="badge"><span class="dot ${{dotClass}}"></span>${{label}}</span>`;

                const queue = (t.queue_time_s === null || t.queue_time_s === undefined) ? '-' : fmtNumber(t.queue_time_s, 3);
                const dur = (t.duration_s === null || t.duration_s === undefined) ? '-' : fmtNumber(t.duration_s, 3);

                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${{t.task_id ?? '-'}}</td>
                    <td>${{t.task_type ?? '-'}}</td>
                    <td>${{badge}}</td>
                    <td>${{t.success === true ? 'true' : (t.success === false ? 'false' : '-')}}</td>
                    <td>${{queue}}</td>
                    <td>${{dur}}</td>
                    <td>${{t.submit_time ?? '-'}}</td>
                    <td>${{t.start_time ?? '-'}}</td>
                    <td>${{t.finish_time ?? '-'}}</td>
                                        <td>${{jsonCell(t.payload)}}</td>
                                        <td>${{jsonCell(t.result)}}</td>
                `;
                tbody.appendChild(row);
            }}
        }}

        renderTable(tableRows);

        document.getElementById('taskSearch').addEventListener('input', (e) => {{
            const q = (e.target.value || '').toLowerCase().trim();
            if (!q) {{
                tableRows = originalRows.slice();
                renderTable(tableRows);
                return;
            }}
            const filtered = originalRows.filter(t =>
                String(t.task_id ?? '').toLowerCase().includes(q) ||
                String(t.task_type ?? '').toLowerCase().includes(q) ||
                String(t.status ?? '').toLowerCase().includes(q)
            );
            tableRows = filtered;
            renderTable(tableRows);
        }});

        document.getElementById('btnSortDur').addEventListener('click', () => {{
            tableRows.sort((a,b) => (b.duration_s ?? -1) - (a.duration_s ?? -1));
            renderTable(tableRows);
        }});
        document.getElementById('btnSortQueue').addEventListener('click', () => {{
            tableRows.sort((a,b) => (b.queue_time_s ?? -1) - (a.queue_time_s ?? -1));
            renderTable(tableRows);
        }});
        document.getElementById('btnReset').addEventListener('click', () => {{
            document.getElementById('taskSearch').value = '';
            tableRows = originalRows.slice();
            renderTable(tableRows);
        }});

        // Task chart
        const labels = originalRows.map(t => String(t.task_id ?? '-'));
        const durations = originalRows.map(t => (t.duration_s ?? null));
        const queues = originalRows.map(t => (t.queue_time_s ?? null));

        echarts.init(document.getElementById('taskChart')).setOption({{
            grid: {{ left: 56, right: 18, top: 40, bottom: 80 }},
            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }},
                formatter: (items) => {{
                    const parts = items.map(it => `${{it.marker}} ${{it.seriesName}}: ${{fmtSeconds(it.value)}}`);
                    return `<div style="font-weight:700;margin-bottom:4px;">${{items[0].axisValue}}</div>` + parts.join('<br/>');
                }}
            }},
            legend: {{ data: ['Duration', 'Queue'] }},
            xAxis: {{
                type: 'category',
                data: labels,
                axisLabel: {{ rotate: 40, color: 'rgba(255,255,255,0.75)' }},
                axisLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.18)' }} }}
            }},
            yAxis: {{
                type: 'value',
                name: 'Seconds',
                axisLabel: {{ color: 'rgba(255,255,255,0.75)' }},
                splitLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.10)' }} }},
                axisLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.18)' }} }}
            }},
            series: [
                {{ name: 'Duration', type: 'bar', data: durations, itemStyle: {{ color: '#7aa2ff' }} }},
                {{ name: 'Queue', type: 'bar', data: queues, itemStyle: {{ color: '#ffcc66' }} }},
            ]
        }});

        // System chart
        const sys = report.system_metrics_v2;
        if (sys && Array.isArray(sys.timeline) && sys.timeline.length) {{
            const t = sys.timeline.map(x => x.t_s);
            const cpu = sys.timeline.map(x => x.cpu_pct);
            const mem = sys.timeline.map(x => x.mem_pct);
            const gpu = sys.timeline.map(x => x.gpu_pct);
            const gpuMemGiB = sys.timeline.map(x => (x.gpu_mem_mb === null || x.gpu_mem_mb === undefined) ? null : (Number(x.gpu_mem_mb) / 1024.0));

            const chart = echarts.init(document.getElementById('sysChart'));
            chart.setOption({{
                grid: {{ left: 56, right: 56, top: 44, bottom: 40 }},
                tooltip: {{ trigger: 'axis' }},
                legend: {{ data: ['CPU %', 'MEM %', 'GPU %', 'GPU Mem (GiB)'] }},
                xAxis: {{
                    type: 'category',
                    data: t,
                    name: 't (s)',
                    axisLabel: {{ color: 'rgba(255,255,255,0.75)' }},
                    axisLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.18)' }} }}
                }},
                yAxis: [
                    {{
                        type: 'value',
                        name: 'Util (%)',
                        axisLabel: {{ color: 'rgba(255,255,255,0.75)' }},
                        splitLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.10)' }} }},
                        axisLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.18)' }} }}
                    }},
                    {{
                        type: 'value',
                        name: 'GPU Mem (GiB)',
                        axisLabel: {{ color: 'rgba(255,255,255,0.75)' }},
                        splitLine: {{ show: false }},
                        axisLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.18)' }} }}
                    }}
                ],
                series: [
                    {{ name: 'CPU %', type: 'line', data: cpu, smooth: true, showSymbol: false }},
                    {{ name: 'MEM %', type: 'line', data: mem, smooth: true, showSymbol: false }},
                    {{ name: 'GPU %', type: 'line', data: gpu, smooth: true, showSymbol: false }},
                    {{ name: 'GPU Mem (GiB)', type: 'line', yAxisIndex: 1, data: gpuMemGiB, smooth: true, showSymbol: false }},
                ]
            }});

            const s = sys.summary || {{}};
            const cpuS = s.cpu_pct ? `CPU avg/max: ${{s.cpu_pct.avg}}/${{s.cpu_pct.max}}%` : '';
            const memS = s.mem_pct ? `MEM avg/max: ${{s.mem_pct.avg}}/${{s.mem_pct.max}}%` : '';
                        let gpuS = '';
                        let gmS = '';
                        if (sys.gpu_available === false) {{
                                gpuS = `GPU: N/A (${{sys.gpu_reason || 'unavailable'}})`;
                        }} else {{
                                gpuS = s.gpu_pct ? `GPU avg/max: ${{s.gpu_pct.avg}}/${{s.gpu_pct.max}}%` : '';
                                gmS = s.gpu_mem_mb ? `GPU Mem avg/max: ${{fmtNumber(Number(s.gpu_mem_mb.avg)/1024.0, 2)}}/${{fmtNumber(Number(s.gpu_mem_mb.max)/1024.0, 2)}} GiB` : '';
                        }}
            document.getElementById('sysSummary').textContent = [cpuS, memS, gpuS, gmS].filter(Boolean).join('  |  ');
        }} else {{
            document.getElementById('sysChart').innerHTML = '<div class="muted" style="padding:16px;">No system metrics collected.</div>';
        }}

        window.addEventListener('resize', () => {{
            try {{ echarts.getInstanceByDom(document.getElementById('taskChart'))?.resize(); }} catch(e) {{}}
            try {{ echarts.getInstanceByDom(document.getElementById('sysChart'))?.resize(); }} catch(e) {{}}
        }});
    </script>
</body>
</html>
"""
