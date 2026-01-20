from locust import HttpUser, task, constant

try:
    from gevent import GreenletExit
except Exception:  # pragma: no cover
    GreenletExit = BaseException

import base64
import json
import threading
import time
import uuid

POLL_INTERVAL = 5
TASK_TIMEOUT = 3600


class AgentUser(HttpUser):
    wait_time = constant(999999)  # 基本不会再跑第二次

    _finished_users = 0
    _finished_lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._active_task_id: str | None = None
        self._active_task_done: bool = False
        self._has_run: bool = False

    def on_start(self):
        # 任务放在 @task 中执行，避免 StopUser 被当成 error 打印堆栈
        return

    def on_stop(self):
        # 当 locust 因 --run-time/CTRL-C 等停止时，尽量回收未完成的任务
        if self._active_task_id and not self._active_task_done:
            self._terminate_task(self._active_task_id)

    @task
    def run_agent_task(self):
        if self._has_run:
            # 只跑一次；其余时间保持 idle，让其它 user 有机会跑完
            time.sleep(999999)
            return

        self._has_run = True
        trace_id = str(uuid.uuid4())
        submit_ts = time.time()

        payload = {
            "user_question": "为了研发导热凝胶，整理分析类似产品的成分和工艺"
        }

        task_id: str | None = None
        self._active_task_id = None
        self._active_task_done = False

        try:
            # ---------- 提交任务 ----------
            with self.client.post(
                "/v1/domain/run",
                json=payload,
                headers={"X-Request-ID": trace_id},
                catch_response=True,
                name="submit_task",
            ) as resp:
                if resp.status_code != 200:
                    resp.failure("create task failed")
                    return

                submit_resp = resp.json()
                task_id = submit_resp["data"]["task_id"]
                self._active_task_id = task_id

            self._emit_json("TASK_PAYLOAD", task_id, payload)
            self._emit_json("TASK_SUBMIT_RESP", task_id, submit_resp)

            print(f"[TASK_SUBMITTED] {task_id} agent {submit_ts}", flush=True)

            # ---------- 轮询状态 ----------
            start_ts = None

            last_data = None

            while time.time() - submit_ts < TASK_TIMEOUT:
                time.sleep(POLL_INTERVAL)

                with self.client.get(
                    f"/v1/task/status/{task_id}",
                    name="poll_status",
                    catch_response=True,
                ) as r:
                    if r.status_code != 200:
                        continue

                    data = r.json().get("data", {})
                    status = data.get("status")
                    last_data = data

                    if status == "RUNNING" and not start_ts:
                        start_ts = time.time()
                        print(f"[TASK_RUNNING] {task_id} {start_ts}", flush=True)

                    if status in ("FINISHED", "FAILED"):
                        end_ts = time.time()
                        success = status == "FINISHED"
                        self._active_task_done = True
                        self._emit_json("TASK_FINAL", task_id, data)
                        print(f"[TASK_DONE] {task_id} {end_ts} {success}", flush=True)

                        # 所有 user 都跑完就立刻结束压测（不等 --run-time）
                        self._mark_finished_and_maybe_quit()
                        return

            # ---------- 超时 ----------
            self._terminate_task(task_id)
            print(f"[TASK_TIMEOUT] {task_id}", flush=True)

            if last_data is not None:
                self._emit_json("TASK_FINAL", task_id, last_data)
            self._mark_finished_and_maybe_quit()

        except GreenletExit:
            # locust 到达 --run-time / 正在退出时会杀掉 greenlet；这里兜底 terminate
            if self._active_task_id and not self._active_task_done:
                self._terminate_task(self._active_task_id)
            raise
        finally:
            # 其它异常/中断也尽量回收
            if self._active_task_id and not self._active_task_done:
                self._terminate_task(self._active_task_id)

    def _emit_json(self, tag: str, task_id: str, obj):
        try:
            raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            b64 = base64.urlsafe_b64encode(raw).decode("ascii")
            print(f"[{tag}] {task_id} {b64}", flush=True)
        except Exception:
            return

    def _expected_users(self) -> int | None:
        opts = getattr(self.environment, "parsed_options", None)
        for key in ("users", "num_users"):
            v = getattr(opts, key, None) if opts is not None else None
            if isinstance(v, int) and v > 0:
                return v
        runner = getattr(self.environment, "runner", None)
        v = getattr(runner, "target_user_count", None)
        if isinstance(v, int) and v > 0:
            return v
        return None

    def _mark_finished_and_maybe_quit(self):
        expected = self._expected_users() or 1
        with self._finished_lock:
            AgentUser._finished_users += 1
            done = AgentUser._finished_users

        if done >= expected:
            try:
                # 尝试优雅退出
                self.environment.runner.quit()
            except Exception:
                pass
            
            # 强制退出进程，确保 run_ramp.py 能捕获到结束信号
            import os
            import signal
            # 给自己发 SIGTERM
            os.kill(os.getpid(), signal.SIGTERM)

    def _terminate_task(self, task_id: str):
        try:
            self.client.post(
                "/v1/task/terminate",
                json={"task_id": task_id},
                name="terminate_task",
            )
        except Exception:
            # 回收接口失败不应影响 locust 退出
            pass
