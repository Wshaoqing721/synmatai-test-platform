import asyncio
import sys
import threading
import base64
import json
import time
import os
import signal
import random
import re
from datetime import datetime
from pathlib import Path

from tests.config import (
    BASE_URL,
    LOCUST_SPAWN_RATE,
    LOCUST_RUN_TIME,
    SYSTEM_MONITOR_INTERVAL,
    REPORT_PATH,
    MEM_AVAILABLE_MIN_GB,
    MEM_AVAILABLE_MIN_RATIO,
)

from tests.core.task_manager import TaskManager
from tests.monitor.system_monitor import SystemMonitor
from tests.reporter.report_writer import ReportWriter


def _b64json_decode(s: str):
    raw = base64.urlsafe_b64decode(s.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def _resolve_report_path(report_path: str | Path) -> Path:
    """Resolve report path. If a directory is given, create filename with time + 6-digit random."""
    p = Path(report_path)
    is_dir_hint = str(report_path).endswith("/") or p.suffix == ""
    if is_dir_hint:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rnd = f"{random.randint(0, 999999):06d}"
        filename = f"ramp_report_{ts}_{rnd}.json"
        return p / filename
    return p


# =========================
# 并发爬坡配置
# =========================
CONCURRENCY_STEPS = [1,2,4,8,16,24]
FAILURE_RATE_THRESHOLD = 0.01




def _should_stop_for_memory(sys_mon: SystemMonitor):
    """Return (stop: bool, reason: str|None) based on latest sys_mon record."""
    try:
        if not getattr(sys_mon, "records", None):
            return False, None
        latest = sys_mon.records[-1] or {}
        if not isinstance(latest, dict):
            return False, None

        avail_mb = latest.get("mem_available_mb")
        total_mb = latest.get("mem_total_mb")

        if avail_mb is None or total_mb is None:
            return False, None

        avail_gb = float(avail_mb) / 1024.0
        total_gb = float(total_mb) / 1024.0
        if total_gb <= 0:
            return False, None

        ratio = avail_gb / total_gb

        if avail_gb < MEM_AVAILABLE_MIN_GB or ratio < MEM_AVAILABLE_MIN_RATIO:
            reason = f"memory_protection: available={avail_gb:.1f}GB ({ratio:.1%}), total={total_gb:.1f}GB"
            return True, reason

        return False, None
    except Exception:
        return False, None


async def run_locust_and_collect(concurrency: int, tm: TaskManager, sys_mon: SystemMonitor):
    print(f"\n🚀 Starting locust (concurrency={concurrency})")

    locustfile = Path(__file__).parent / "locustfile.py"

    locust_cmd = [
        "locust",
        "-f", str(locustfile),
        "--headless",
        "-u", str(concurrency),
        "-r", str(LOCUST_SPAWN_RATE),
        "-t", LOCUST_RUN_TIME,
        "--host", BASE_URL,
    ]

    proc = await asyncio.create_subprocess_exec(
        *locust_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )

    assert proc.stdout is not None

    should_stop = False
    stop_reason = None
    done_count = 0

    tag_pattern = re.compile(r"^\[(?P<tag>[A-Z0-9_]+)]\s+")

    async for raw in proc.stdout:
        line = raw.decode().strip()
        if not line:
            continue

        print(line)

        tag_match = tag_pattern.match(line)
        tag = tag_match.group("tag") if tag_match else ""
        parts = line.split()

        if tag.endswith("_SUBMITTED"):
            if len(parts) >= 3:
                task_id = parts[1]
                ts = parts[-1]
                tm.on_submit(task_id, float(ts))

        elif tag == "TASK_PAYLOAD":
            _, task_id, b64 = line.split(maxsplit=2)
            tm.on_meta(task_id, payload=_b64json_decode(b64))

        elif tag == "TASK_SUBMIT_RESP":
            _, task_id, b64 = line.split(maxsplit=2)
            tm.on_meta(task_id, submit_resp=_b64json_decode(b64))

        elif tag == "TASK_FINAL":
            _, task_id, b64 = line.split(maxsplit=2)
            tm.on_meta(task_id, final=_b64json_decode(b64))

        elif tag.endswith("_RUNNING"):
            if len(parts) >= 3:
                task_id = parts[1]
                ts = parts[-1]
                tm.on_start(task_id, float(ts))

        elif tag == "RUN_DONE":
            done_count += 1
            print(f"⏳ RUN_DONE detected: done_count={done_count}/{concurrency}")
            if done_count >= concurrency:
                print(f"✅ Reached done_count={concurrency}, stop current step")
                should_stop = True

        elif tag.endswith("_DONE"):
            if len(parts) >= 4:
                task_id = parts[1]
                ts = parts[2]
                success = parts[3]
                tm.on_finish(task_id, float(ts), success == "True")

        elif tag == "RUN_TIMEOUT":
            done_count += 1
            print(f"⏱️ RUN_TIMEOUT detected: done_count={done_count}/{concurrency}")
            if done_count >= concurrency:
                print(f"✅ Reached done_count={concurrency}, stop current step")
                should_stop = True

        elif tag.endswith("_TIMEOUT"):
            _, task_id = line.split(maxsplit=1)
            tm.on_finish(task_id, time.time(), success=False)

        elif line.startswith("[TASK_ERROR]"):
            # 格式: [TASK_ERROR] trace_id message...
            parts = line.split(maxsplit=2)
            trace_id = parts[1] if len(parts) > 1 else f"error_{done_count}"
            tm.on_submit(trace_id, time.time())
            tm.on_finish(trace_id, time.time(), success=False)
            done_count += 1
            if done_count >= concurrency:
                print(f"✅ Reached done_count={concurrency}, stop current step")
                should_stop = True

        # ========= 内存保护检查（使用 available） =========
        mem_stop, mem_reason = _should_stop_for_memory(sys_mon)
        if mem_stop:
            stop_reason = mem_reason
            print(f"🛑 {stop_reason}")
            should_stop = True

        if should_stop:
            if proc.returncode is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except Exception:
                    proc.terminate()
            break

    if proc.returncode is None:
        if should_stop:
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    proc.kill()
                await proc.wait()
        else:
            await proc.wait()
    print("🏁 Locust finished")

    return stop_reason


def is_stable(tm: TaskManager, concurrency: int):
    summary = tm.summary()

    if summary["task_count"] < concurrency:
        return False, "no completed tasks"

    if summary["failure_rate"] > FAILURE_RATE_THRESHOLD:
        return False, f"failure_rate={summary['failure_rate']:.2%}"

    return True, "stable"


async def main():
    ramp_results = []
    max_stable_concurrency = 0

    for concurrency in CONCURRENCY_STEPS:
        print("\n==============================")
        print(f"📈 Ramp test @ concurrency={concurrency}")
        print("==============================")

        tm = TaskManager()
        sys_mon = SystemMonitor(SYSTEM_MONITOR_INTERVAL)

        # ---------- 启动系统监控 ----------
        sys_thread = threading.Thread(target=sys_mon.run, daemon=True)
        sys_thread.start()

        try:
            stop_reason = await run_locust_and_collect(concurrency, tm, sys_mon)
        finally:
            sys_mon.stop()
            sys_thread.join()

        summary = tm.summary()
        stable, reason = is_stable(tm, concurrency)
        if stop_reason:
            stable = False
            reason = stop_reason

        # 把每个档位的任务/系统指标也塞进爬坡报告，便于回溯分析
        step_tasks = tm.export_tasks()
        step_sys_metrics = list(getattr(sys_mon, "records", []) or [])

        ramp_results.append({
            "concurrency": concurrency,
            "stable": stable,
            "reason": reason,
            "metrics": summary,
            "tasks": step_tasks,
            "system_metrics": step_sys_metrics,
        })

        print(f"📊 Result: {reason}")
        print(summary)

        if stable:
            max_stable_concurrency = concurrency
        else:
            print("⛔ System unstable, stop ramp-up")
            break

    # ---------- 输出最终报告 ----------
    final_report = {
        "max_stable_concurrency": max_stable_concurrency,
        "ramp_results": ramp_results,
    }

    report_path = _resolve_report_path(REPORT_PATH)
    writer = ReportWriter(
        ws_monitor=None,
        sys_monitor=None,
        task_manager=None,
    )
    writer.write_ramp_report(report_path, final_report)

    print("\n🎯 FINAL RESULT")
    print(f"✅ Max stable concurrency = {max_stable_concurrency}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⛔ Interrupted")
        sys.exit(130)
