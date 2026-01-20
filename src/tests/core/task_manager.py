import statistics


class TaskManager:
    def __init__(self):
        self.tasks = {}

    def on_submit(self, task_id, ts):
        t = self.tasks.get(task_id)
        if t is None:
            self.tasks[task_id] = {
                "task_id": task_id,
                "submit_ts": ts,
                "start_ts": None,
                "end_ts": None,
                "status": "SUBMITTED",
                "success": None,
                "payload": None,
                "submit_resp": None,
                "final": None,
            }
            return

        # meta 可能先到（TASK_PAYLOAD/TASK_SUBMIT_RESP），这里不要覆盖已有字段
        t["task_id"] = task_id
        t["submit_ts"] = ts
        t.setdefault("start_ts", None)
        t.setdefault("end_ts", None)
        t["status"] = "SUBMITTED"
        t.setdefault("success", None)
        t.setdefault("payload", None)
        t.setdefault("submit_resp", None)
        t.setdefault("final", None)

    def on_meta(self, task_id, payload=None, submit_resp=None, final=None):
        t = self.tasks.get(task_id)
        if not t:
            # meta 可能先于 submit 事件到达；兜底创建
            self.on_submit(task_id, ts=None)
            t = self.tasks.get(task_id)
        if not t:
            return

        if payload is not None:
            t["payload"] = payload
        if submit_resp is not None:
            t["submit_resp"] = submit_resp
        if final is not None:
            t["final"] = final

    def on_start(self, task_id, ts):
        t = self.tasks.get(task_id)
        if t:
            t["start_ts"] = ts
            t["status"] = "RUNNING"

    def on_finish(self, task_id, ts, success=True):
        t = self.tasks.get(task_id)
        if t:
            t["end_ts"] = ts
            t["success"] = success
            t["status"] = "DONE" if success else "FAILED"

    # ---------- 指标 ----------
    def durations(self):
        return [
            t["end_ts"] - t["start_ts"]
            for t in self.tasks.values()
            if t["start_ts"] is not None and t["end_ts"] is not None
        ]

    def queue_times(self):
        return [
            t["start_ts"] - t["submit_ts"]
            for t in self.tasks.values()
            if t["start_ts"] is not None
        ]

    def failure_rate(self):
        total = len(self.tasks)
        failed = sum(1 for t in self.tasks.values() if t["status"] == "FAILED")
        return failed / total if total else 0

    def max_concurrency(self):
        events = []
        for t in self.tasks.values():
            if t["start_ts"] and t["end_ts"]:
                events.append((t["start_ts"], +1))
                events.append((t["end_ts"], -1))

        events.sort()
        cur = peak = 0
        for _, delta in events:
            cur += delta
            peak = max(peak, cur)
        return peak

    def summary(self):
        d = self.durations()
        q = self.queue_times()

        return {
            "task_count": len(self.tasks),
            "max_concurrency": self.max_concurrency(),
            "avg_duration": statistics.mean(d) if d else None,
            "p95_duration": statistics.quantiles(d, n=20)[18] if len(d) >= 20 else None,
            "avg_queue_time": statistics.mean(q) if q else None,
            "failure_rate": self.failure_rate(),
        }

    # ---------- 给 ReportWriter 用 ----------
    def export_tasks(self):
        result = {}

        for tid, t in self.tasks.items():
            result[tid] = {
                "task_id": tid,
                "submit_ts": t["submit_ts"],
                "start_ts": t["start_ts"],
                "finish_ts": t["end_ts"],
                "success": t["success"],
                "payload": t.get("payload"),
                "submit_resp": t.get("submit_resp"),
                "final": t.get("final"),
                "duration": (
                    t["end_ts"] - t["start_ts"]
                    if t["end_ts"] and t["start_ts"]
                    else None
                ),
                "queue_time": (
                    t["start_ts"] - t["submit_ts"]
                    if t["start_ts"]
                    else None
                ),
                "status": t["status"],
            }

        return result
