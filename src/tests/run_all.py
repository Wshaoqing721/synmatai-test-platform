# tests/run_all.py
import asyncio
import contextlib
import sys
import threading
import base64
import json
from pathlib import Path

from tests.config import (
    BASE_URL,
    LOCUST_USERS,
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


async def run_locust_and_collect(locust_cmd, tm: TaskManager):
    print("🚀 Starting locust...")
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


async def main():
    tm = TaskManager()
    sys_mon = SystemMonitor(SYSTEM_MONITOR_INTERVAL)

    # ---------- 启动系统监控 ----------
    sys_thread = threading.Thread(target=sys_mon.run, daemon=True)
    sys_thread.start()

    # ---------- Locust ----------
    locustfile = Path(__file__).parent / "locustfile.py"
    locust_cmd = [
        "locust",
        "-f", str(locustfile),
        "--headless",
        "-u", str(LOCUST_USERS),
        "-r", str(LOCUST_SPAWN_RATE),
        "-t", LOCUST_RUN_TIME,
        "--host", BASE_URL,
    ]

    try:
        await run_locust_and_collect(locust_cmd, tm)
    finally:
        # ---------- 停止监控 ----------
        sys_mon.stop()
        sys_thread.join()

        # ---------- 生成报告 ----------
        writer = ReportWriter(
            ws_monitor=None,
            sys_monitor=sys_mon,
            task_manager=tm
        )
        writer.write(REPORT_PATH)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⛔ Interrupted")
        sys.exit(130)
