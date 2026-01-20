import asyncio
import sys
import threading
import base64
import json
from pathlib import Path

from tests.config import (
    BASE_URL,
    LOCUST_SPAWN_RATE,
    LOCUST_RUN_TIME,
    SYSTEM_MONITOR_INTERVAL,
    REPORT_PATH,
)

from tests.core.task_manager import TaskManager
from tests.monitor.system_monitor import SystemMonitor
from tests.reporter.report_writer import ReportWriter


def _b64json_decode(s: str):
    raw = base64.urlsafe_b64decode(s.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


# =========================
# 并发爬坡配置
# =========================
CONCURRENCY_STEPS = [1]
FAILURE_RATE_THRESHOLD = 0.01
MIN_TASKS = 1


async def run_locust_and_collect(concurrency: int, tm: TaskManager):
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
    )

    assert proc.stdout is not None

    async for raw in proc.stdout:
        line = raw.decode().strip()
        if not line:
            continue

        print(line)

        if line.startswith("[TASK_SUBMITTED]"):
            _, task_id, _, ts = line.split()
            tm.on_submit(task_id, float(ts))

        elif line.startswith("[TASK_PAYLOAD]"):
            _, task_id, b64 = line.split(maxsplit=2)
            tm.on_meta(task_id, payload=_b64json_decode(b64))

        elif line.startswith("[TASK_SUBMIT_RESP]"):
            _, task_id, b64 = line.split(maxsplit=2)
            tm.on_meta(task_id, submit_resp=_b64json_decode(b64))

        elif line.startswith("[TASK_FINAL]"):
            _, task_id, b64 = line.split(maxsplit=2)
            tm.on_meta(task_id, final=_b64json_decode(b64))

        elif line.startswith("[TASK_RUNNING]"):
            _, task_id, ts = line.split()
            tm.on_start(task_id, float(ts))

        elif line.startswith("[TASK_DONE]"):
            _, task_id, ts, success = line.split()
            tm.on_finish(task_id, float(ts), success == "True")

    await proc.wait()
    print("🏁 Locust finished")


def is_stable(tm: TaskManager):
    summary = tm.summary()

    if summary["task_count"] < MIN_TASKS:
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
            await run_locust_and_collect(concurrency, tm)
        finally:
            sys_mon.stop()
            sys_thread.join()

        summary = tm.summary()
        stable, reason = is_stable(tm)

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

    writer = ReportWriter(
        ws_monitor=None,
        sys_monitor=None,
        task_manager=None,
    )
    writer.write_ramp_report(REPORT_PATH, final_report)

    print("\n🎯 FINAL RESULT")
    print(f"✅ Max stable concurrency = {max_stable_concurrency}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⛔ Interrupted")
        sys.exit(130)
