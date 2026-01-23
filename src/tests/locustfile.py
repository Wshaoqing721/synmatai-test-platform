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

TASK_PIPELINE = [
    {
        "submit_path": "/v2/rd/run-sop-driven-design",
        "status_path_template": "/v1/task/status/{task_id}",
        "submit_name": "submit_sop_task",
        "poll_name": "poll_sop_status",
        "submit_tag": "SOP",
        "payload": {
            "design_type": "ocr",
            "project_name": "通用SOP驱动研发项目",
            "user_requirements_text": "我需要一款高折射率（接近1.50），并且固化后应力尽可能低的OCR，用于厚玻璃的贴合。",
            "output_language": "chinese",
            "async_mode": True,
        },
        "variants": [
            {
                "design_type": "ocr",
                "project_name": "通用SOP驱动研发项目",
                "user_requirements_text": "我需要一款高折射率（接近1.50），并且固化后应力尽可能低的OCR，用于厚玻璃的贴合。",
                "output_language": "chinese",
                "async_mode": True,
            },
            {
                "design_type": "rtv",
                "project_name": "RTV硅橡胶研发项目",
                "user_requirements_text": "需要一款室温硫化硅橡胶，具有优良的耐候性与电气绝缘性。",
                "output_language": "chinese",
                "async_mode": True,
            },
            {
                "design_type": "silicone_psa",
                "project_name": "有机硅压敏胶研发项目",
                "user_requirements_text": "需要一款低残留、耐高温的有机硅压敏胶，用于精密贴合。",
                "output_language": "chinese",
                "async_mode": True,
            },
            {
                "design_type": "graphene_thermal_pad",
                "project_name": "石墨烯导热垫研发工作流",
                "user_requirements_text": "需要一款高导热、耐压缩的石墨烯导热垫材料，用于散热模组。",
                "output_language": "chinese",
                "async_mode": True,
            },
            {
                "design_type": "inductor_adhesive",
                "project_name": "电感胶研发工作流",
                "user_requirements_text": "需要一款高强度、耐热冲击的电感胶，适配线圈固定与封装。",
                "output_language": "chinese",
                "async_mode": True,
            },
            {
                "design_type": "optical_adhesive",
                "project_name": "光学粘结胶敏捷开发工作流",
                "user_requirements_text": "需要一款高透过率、低黄变的光学粘结胶，用于显示与光学器件贴合。",
                "output_language": "chinese",
                "async_mode": True,
            },
            {
                "design_type": "photoresist",
                "project_name": "光刻胶研发工作流",
                "user_requirements_text": "需要一款分辨率高、耐刻蚀的光刻胶，适配先进制程。",
                "output_language": "chinese",
                "async_mode": True,
            },
            {
                "design_type": "thermal_gel",
                "project_name": "热导胶研发工作流",
                "user_requirements_text": "需要一款低挥发、高导热的热导胶，用于电子器件散热。",
                "output_language": "chinese",
                "async_mode": True,
            },
            {
                "design_type": "underfill",
                "project_name": "Underfill敏捷开发工作流",
                "user_requirements_text": "需要一款低黏度、低翘曲的Underfill材料，用于芯片封装。",
                "output_language": "chinese",
                "async_mode": True,
            },
            {
                "design_type": "pspi",
                "project_name": "PFAS-Free PSPI研发工作流",
                "user_requirements_text": "需要一款无PFAS的光敏性聚酰亚胺，兼顾耐热与图形解析度。",
                "output_language": "chinese",
                "async_mode": True,
            },
            {
                "design_type": "oca",
                "project_name": "折叠屏OCA研发工作流",
                "user_requirements_text": "需要一款耐折、低雾度的OCA胶，用于折叠屏贴合。",
                "output_language": "chinese",
                "async_mode": True,
            },
            {
                "design_type": "pet_baijiu",
                "project_name": "白酒包装用PET材料研发工作流",
                "user_requirements_text": "需要一款适合白酒包装的PET材料，具备阻隔性与透明性。",
                "output_language": "chinese",
                "async_mode": True,
            },
            {
                "design_type": "pet_baijiu_packaging",
                "project_name": "白酒包装用PET材料",
                "user_requirements_text": "需要一款适合白酒包装的PET方案，兼顾成型与抗冲击性能。",
                "output_language": "chinese",
                "async_mode": True,
            },
        ],
    },
]
# TASK_PIPELINE = [
#     {
#         "submit_path": "/v1/plot/heatmap/run",
#         "status_path_template": "/v1/plot/task/status/{task_id}",
#         "submit_name": "submit_heatmap_task",
#         "poll_name": "poll_heatmap_status",
#         "submit_tag": "HEATMAP",
#         "payload": {
#             "query_direction": "人工智能 大模型",
#             "start_year": 2023,
#             "end_year": 2025,
#             "country": "WO",
#             "keyword_num": 2,
#             "async_mode": True,
#             "output_subdir": "plots",
#         },
#     },
#     {
#         "submit_path": "/v2/rd/run-sop-driven-design",
#         "status_path_template": "/v1/task/status/{task_id}",
#         "submit_name": "submit_sop_task",
#         "poll_name": "poll_sop_status",
#         "submit_tag": "SOP",
#         "payload": {
#             "design_type": "ocr",
#             "project_name": "通用SOP驱动研发项目",
#             "user_requirements_text": "我需要一款高折射率（接近1.50），并且固化后应力尽可能低的OCR，用于厚玻璃的贴合。",
#             "output_language": "chinese",
#             "async_mode": True,
#         },
#     },
#     {
#         "submit_path": "/v1/domain/run",
#         "status_path_template": "/v1/task/status/{task_id}",
#         "submit_name": "submit_task",
#         "poll_name": "poll_status",
#         "submit_tag": "TASK",
#         "payload": {
#             "user_question": "面向电子与结构连接应用的胶黏剂专利布局及其对产业化工艺选择的影响"
#         },
#     },
# ]


class BaseAsyncTaskUser(HttpUser):
    wait_time = constant(999999)  # 基本不会再跑第二次

    abstract = True

    _user_counter = 0
    _user_counter_lock = threading.Lock()
    _finished_users = 0
    _finished_lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._active_task_id: str | None = None
        self._active_task_done: bool = False
        self._has_run: bool = False
        with self._user_counter_lock:
            BaseAsyncTaskUser._user_counter += 1
            self._user_index = BaseAsyncTaskUser._user_counter - 1

    def on_start(self):
        # 任务放在 @task 中执行，避免 StopUser 被当成 error 打印堆栈
        return

    def on_stop(self):
        # 当 locust 因 --run-time/CTRL-C 等停止时，尽量回收未完成的任务
        if self._active_task_id and not self._active_task_done:
            self._terminate_task(self._active_task_id)

    def _run_async_task(
        self,
        submit_path: str,
        submit_payload: dict,
        status_path_template: str,
        submit_name: str,
        poll_name: str,
        submit_tag: str,
    ):
        trace_id = str(uuid.uuid4())
        submit_ts = time.time()

        task_id: str | None = None
        self._active_task_id = None
        self._active_task_done = False

        try:
            # ---------- 提交任务 ----------
            with self.client.post(
                submit_path,
                json=submit_payload,
                headers={"X-Request-ID": trace_id},
                catch_response=True,
                name=submit_name,
            ) as resp:
                if resp.status_code != 200:
                    self._emit_json("TASK_PAYLOAD", trace_id, submit_payload)
                    self._emit_json(
                        "TASK_SUBMIT_RESP",
                        trace_id,
                        {"status_code": resp.status_code, "text": resp.text},
                    )
                    err_msg = f"create task failed: {resp.status_code} - {resp.text}"
                    print(f"[TASK_ERROR] {trace_id} {err_msg}", flush=True)
                    resp.failure(err_msg)
                    return

                submit_resp = resp.json()
                task_id = submit_resp["data"]["task_id"]
                self._active_task_id = task_id

            self._emit_json("TASK_PAYLOAD", task_id, submit_payload)
            self._emit_json("TASK_SUBMIT_RESP", task_id, submit_resp)

            print(f"[{submit_tag}_SUBMITTED] {task_id} {submit_ts}", flush=True)

            # ---------- 轮询状态 ----------
            start_ts = None

            last_data = None

            while time.time() - submit_ts < TASK_TIMEOUT:
                time.sleep(POLL_INTERVAL)

                with self.client.get(
                    status_path_template.format(task_id=task_id),
                    name=poll_name,
                    catch_response=True,
                ) as r:
                    if r.status_code != 200:
                        continue

                    data = r.json().get("data", {})
                    status = data.get("status")
                    last_data = data

                    if status == "RUNNING" and not start_ts:
                        start_ts = time.time()
                        print(f"[{submit_tag}_RUNNING] {task_id} {start_ts}", flush=True)

                    if status in ("FINISHED", "FAILED"):
                        end_ts = time.time()
                        success = status == "FINISHED"
                        self._active_task_done = True
                        self._emit_json("TASK_FINAL", task_id, data)
                        print(f"[{submit_tag}_DONE] {task_id} {end_ts} {success}", flush=True)

                        return task_id

            # ---------- 超时 ----------
            if task_id:
                self._terminate_task(task_id)
            print(f"[{submit_tag}_TIMEOUT] {task_id}", flush=True)

            if last_data is not None:
                self._emit_json("TASK_FINAL", task_id, last_data)
            return task_id

        except GreenletExit:
            # locust 到达 --run-time / 正在退出时会杀掉 greenlet；这里兜底 terminate
            if self._active_task_id and not self._active_task_done:
                self._terminate_task(self._active_task_id)
            raise
        finally:
            # 其它异常/中断也尽量回收
            if self._active_task_id and not self._active_task_done:
                self._terminate_task(self._active_task_id)

        return None

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
        expected = self._expected_users()
        if not expected:
            return
        with self._finished_lock:
            type(self)._finished_users += 1
            done = type(self)._finished_users

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
            print(f"🛑 [TASK_TERMINATE] {task_id}", flush=True)
            resp = self.client.post(
                "/v1/task/terminate",
                json={"task_id": task_id},
                name="terminate_task",
            )
            
            self._emit_json(
                "TASK_TERMINATE_RESP",
                task_id,
                {"status_code": resp.status_code, "text": resp.text},
            )

        except Exception:
            # 回收接口失败不应影响 locust 退出
            print(f"⚠️ [TASK_TERMINATE_ERROR] {task_id}", flush=True)

class PipelineUser(BaseAsyncTaskUser):
    @task
    def run_pipeline(self):
        if self._has_run:
            time.sleep(999999)
            return

        self._has_run = True
        pipeline_start = time.time()
        print(f"🚀 [PIPELINE_START] {pipeline_start}", flush=True)

        for spec in TASK_PIPELINE:
            step_start = time.time()
            print(f"▶️ [PIPELINE_STEP_START] {spec['submit_tag']} {step_start}", flush=True)
            payload = _resolve_payload(spec, self._user_index)
            self._run_async_task(
                submit_path=spec["submit_path"],
                submit_payload=payload,
                status_path_template=spec["status_path_template"],
                submit_name=spec["submit_name"],
                poll_name=spec["poll_name"],
                submit_tag=spec["submit_tag"],
            )
            step_end = time.time()
            print(f"✅ [PIPELINE_STEP_DONE] {spec['submit_tag']} {step_end}", flush=True)

        pipeline_end = time.time()
        print(f"🏁 [PIPELINE_DONE] {pipeline_end}", flush=True)
        print(f"[RUN_DONE] pipeline {pipeline_end}", flush=True)
        self._mark_finished_and_maybe_quit()


def _resolve_payload(spec: dict, user_index: int) -> dict:
    base = spec.get("payload", {})
    variants = spec.get("variants") or []
    if variants:
        variant = variants[user_index % len(variants)]
        return {**base, **variant}
    return base
