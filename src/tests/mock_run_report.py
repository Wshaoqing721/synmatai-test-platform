# tests/mock_run_report.py
import time
import threading
from pathlib import Path

from tests.core.task_manager import TaskManager
from tests.monitor.system_monitor import SystemMonitor
from tests.reporter.report_writer import ReportWriter
from tests.config import REPORT_PATH


# ---------- Mock SystemMonitor ----------
class MockSystemMonitor(SystemMonitor):
    def run(self):
        """不实际监控，只生成模拟数据"""
        self.records = []
        now = time.time()
        for i in range(20):
            self.records.append({
                "ts": now + i * 1,
                "cpu": 20 + i,           # CPU %
                "mem": 50 + i,           # MEM %
                "gpu": 10 + i,           # GPU %
                "gpu_mem": 1000 + i*5    # GPU MB
            })


# ---------- Mock TaskManager ----------
tm = TaskManager()
now = time.time()
# 模拟 5 个任务
for i in range(5):
    tid = f"task_{i}"
    submit_ts = now + i
    start_ts = submit_ts + 1
    finish_ts = start_ts + (i + 1) * 2
    tm.on_submit(tid, submit_ts)
    tm.on_start(tid, start_ts)
    tm.on_finish(tid, finish_ts, success=(i % 2 == 0))  # 偶数任务成功

# ---------- Mock SystemMonitor ----------
sys_mon = MockSystemMonitor(interval=1)
sys_mon.run()  # 直接生成数据，无循环

# ---------- 生成报告 ----------
writer = ReportWriter(
    ws_monitor=None,
    task_manager=tm,
    sys_monitor=sys_mon
)
writer.write(REPORT_PATH)

print("✅ Mock report generated!")
