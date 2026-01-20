# tests/client/ws_monitor.py
import asyncio
import json
import time
import websockets


class WebSocketTaskMonitor:
    def __init__(self, user_ws_url, logs_ws_base, token, *, print_logs: bool = True, task_manager=None):
        self.user_ws_url = user_ws_url
        self.logs_ws_base = logs_ws_base
        self.token = token
        self.print_logs = print_logs

        self.start_ts = time.time()
        self.running = True

        self.tasks = {}      # task_id -> task data
        self.log_tasks = {}  # task_id -> asyncio.Task
        self._done_events = {}  # task_id -> asyncio.Event
        self.tm = task_manager

    # ---------- 公共 ----------
    async def on_task_submitted(self, task_id):
        if self.tm is not None:
            self.tm.on_submit(task_id, time.time())
        self._ensure_task(task_id)

    async def on_task_running(self, task_id):
        if self.tm is not None:
            self.tm.on_start(task_id, time.time())
        self._ensure_task(task_id)["status_timeline"].append({
            "ts": time.time() - self.start_ts,
            "status": "running",
            "progress": None,
        })

    async def on_task_done(self, task_id, success=True):
        if self.tm is not None:
            self.tm.on_finish(task_id, time.time(), success)
        self._ensure_task(task_id)["status_timeline"].append({
            "ts": time.time() - self.start_ts,
            "status": "success" if success else "failed",
            "progress": 100,
        })
        self._done_events.setdefault(task_id, asyncio.Event()).set()

    def stop(self):
        self.running = False
        for t in self.log_tasks.values():
            t.cancel()

    def _ws_headers(self):
        if not self.token:
            return None
        # websockets>=15 uses `additional_headers`
        return [("Authorization", f"Bearer {self.token}")]

    def _ensure_task(self, task_id: str, **initial_fields):
        task = self.tasks.setdefault(task_id, {
            "task_id": task_id,
            "task_type": initial_fields.get("task_type"),
            "conversation_id": initial_fields.get("conversation_id"),
            "status_timeline": [],
            "logs": [],
        })
        self._done_events.setdefault(task_id, asyncio.Event())
        return task

    @staticmethod
    def _is_terminal_status(status: str | None) -> bool:
        if not status:
            return False
        return str(status).lower() in {
            "done",
            "completed",
            "complete",
            "success",
            "succeeded",
            "failed",
            "error",
            "cancelled",
            "canceled",
        }

    @staticmethod
    def _looks_like_log_message(msg: dict) -> bool:
        return "task_id" in msg and ("detail" in msg or "progress" in msg)

    @staticmethod
    def _looks_like_status_message(msg: dict) -> bool:
        return "task_id" in msg and "status" in msg

    def _maybe_mark_done_from_log(self, task_id: str, msg: dict) -> None:
        progress = msg.get("progress")
        detail = (msg.get("detail") or "").lower()

        if isinstance(progress, (int, float)) and progress >= 100:
            self._done_events[task_id].set()
            return

        terminal_keywords = ["completed", "complete", "done", "success", "failed", "error", "cancelled", "canceled", "finish", "finished"]
        terminal_keywords_cn = ["完成", "结束", "失败", "异常", "报错", "已完成"]
        if any(k in detail for k in terminal_keywords) or any(k.lower() in detail for k in terminal_keywords_cn):
            self._done_events[task_id].set()

    def is_task_done(self, task_id: str) -> bool:
        ev = self._done_events.get(task_id)
        return bool(ev and ev.is_set())

    async def wait_for_tasks_done(self, task_ids, timeout: float = 600.0, poll_interval: float = 0.5) -> bool:
        end_ts = time.monotonic() + timeout
        task_ids = list(task_ids)

        # If we have no tasks, nothing to wait for.
        if not task_ids:
            return True

        while self.running and time.monotonic() < end_ts:
            pending = [tid for tid in task_ids if not self.is_task_done(tid)]
            if not pending:
                return True
            await asyncio.sleep(poll_interval)

        return False

    # ---------- 用户状态监听 ----------
    async def listen_user_status(self):
        while self.running:
            try:
                async with websockets.connect(self.user_ws_url, additional_headers=self._ws_headers()) as ws:
                    while self.running:
                        try:
                            msg = json.loads(await ws.recv())
                        except Exception:
                            break

                        # Compatible with different backend formats
                        if msg.get("event") == "task_status" or msg.get("type") == "task_status" or self._looks_like_status_message(msg):
                            self._handle_task_status(msg)
            except Exception:
                # backoff and retry
                await asyncio.sleep(1)

    def _handle_task_status(self, msg):
        task_id = msg["task_id"]

        task = self._ensure_task(
            task_id,
            task_type=msg.get("task_type"),
            conversation_id=msg.get("conversation_id"),
        )

        task["status_timeline"].append({
            "ts": time.time() - self.start_ts,
            "status": msg.get("status"),
            "progress": msg.get("progress")
        })

        if self._is_terminal_status(msg.get("status")):
            self._done_events[task_id].set()

    # ---------- 任务日志监听（由外部触发） ----------
    async def listen_task_logs(self, task_id, task_type: str | None = None):
        if task_id in self.log_tasks:
            return

        # Do not force trailing slash; some servers don't accept it.
        url = f"{self.logs_ws_base}/{task_id}"

        self._ensure_task(task_id, task_type=task_type)

        async def _logger():
            while self.running:
                try:
                    async with websockets.connect(url, additional_headers=self._ws_headers()) as ws:
                        while self.running:
                            try:
                                msg = json.loads(await ws.recv())
                            except Exception:
                                break

                            # Some backends don't include an `event` field for logs.
                            if msg.get("event") not in (None, "log_update") and not self._looks_like_log_message(msg):
                                continue

                            record = {
                                "ts": time.time() - self.start_ts,
                                "progress": msg.get("progress"),
                                "detail": msg.get("detail"),
                                "created_at": msg.get("created_at"),
                            }
                            self._ensure_task(task_id)["logs"].append(record)
                            self._maybe_mark_done_from_log(task_id, msg)

                            if self.print_logs:
                                p = record.get("progress")
                                d = record.get("detail")
                                print(f"[LOG] {task_id} {p}: {d}")
                except Exception:
                    await asyncio.sleep(1)

        self.log_tasks[task_id] = asyncio.create_task(_logger())

    # ---------- 主入口 ----------
    async def run(self):
        await self.listen_user_status()

