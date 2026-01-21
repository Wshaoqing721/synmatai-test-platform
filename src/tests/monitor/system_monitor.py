import time
import psutil
import subprocess
import shutil
import platform
from typing import Any

class SystemMonitor:
    def __init__(self, interval=2):
        self.interval = interval
        self.running = False
        self.records = []

        self.gpu_available = bool(shutil.which("nvidia-smi"))
        self.gpu_reason = None if self.gpu_available else "nvidia-smi not found"

        self.server_info = self._get_server_info()
        self.gpu_info = self._get_gpu_info() if self.gpu_available else []

    def _get_cpu_model(self) -> str | None:
        # Best-effort: /proc/cpuinfo on Linux
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip() or None
        except Exception:
            pass
        try:
            p = platform.processor()
            return p or None
        except Exception:
            return None

    def _get_server_info(self) -> dict[str, Any]:
        vm = psutil.virtual_memory()
        return {
            "hostname": platform.node(),
            "os": platform.platform(),
            "python": platform.python_version(),
            "cpu_model": self._get_cpu_model(),
            "cpu_logical_cores": psutil.cpu_count(logical=True),
            "cpu_physical_cores": psutil.cpu_count(logical=False),
            "mem_total_mb": int(vm.total / 1024 / 1024),
        }

    def _get_gpu_info(self) -> list[dict[str, Any]]:
        if not self.gpu_available:
            return []
        try:
            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,driver_version,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                encoding="utf-8",
            )
            gpus: list[dict[str, Any]] = []
            for line in out.strip().splitlines():
                if not line.strip():
                    continue
                parts = [p.strip() for p in line.split(",")]
                # index, name, driver_version, memory.total
                if len(parts) >= 4:
                    gpus.append(
                        {
                            "index": int(parts[0]),
                            "name": parts[1],
                            "driver_version": parts[2],
                            "mem_total_mb": int(float(parts[3])),
                        }
                    )
            return gpus
        except Exception:
            return []

    def _gpu_usage(self):
        """Return per-GPU util/memory used/total, plus legacy aggregate fields.

        Returns:
            (gpu_utils, gpu_mem_used, gpu_mem_total, legacy_gpu, legacy_gpu_mem)
        """
        if not self.gpu_available:
            return None, None, None, None, None
        try:
            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                encoding="utf-8"
            )
            # Handle multiple GPUs (output may contain multiple lines)
            # Example output:
            # 0, 989
            # 52, 13442
            lines = out.strip().splitlines()
            if not lines:
                return None, None, None, None, None

            gpu_utils: list[int | None] = []
            gpu_mem_used: list[int | None] = []
            gpu_mem_total: list[int | None] = []

            for line in lines:
                if not line.strip():
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    try:
                        gpu_utils.append(int(float(parts[0])))
                    except Exception:
                        gpu_utils.append(None)
                    try:
                        gpu_mem_used.append(int(float(parts[1])))
                    except Exception:
                        gpu_mem_used.append(None)
                    try:
                        gpu_mem_total.append(int(float(parts[2])))
                    except Exception:
                        gpu_mem_total.append(None)

            # Legacy fields kept for backward compatibility
            legacy_gpu = None
            legacy_gpu_mem = None
            utils_v = [u for u in gpu_utils if u is not None]
            mem_v = [m for m in gpu_mem_used if m is not None]
            if utils_v:
                legacy_gpu = int(max(utils_v))  # bottleneck GPU util
            if mem_v:
                legacy_gpu_mem = int(sum(mem_v))  # total used across all GPUs

            return gpu_utils, gpu_mem_used, gpu_mem_total, legacy_gpu, legacy_gpu_mem
        except Exception:
            return None, None, None, None, None

    def run(self):
        self.running = True
        while self.running:
            cpu = psutil.cpu_percent()
            vm = psutil.virtual_memory()
            mem_pct = vm.percent
            mem_total_mb = int(vm.total / 1024 / 1024)
            mem_used_mb = int(vm.used / 1024 / 1024)
            mem_available_mb = int(getattr(vm, "available", 0) / 1024 / 1024)

            gpu_utils, gpu_mem_used, gpu_mem_total, legacy_gpu, legacy_gpu_mem = self._gpu_usage()

            self.records.append({
                "ts": time.time(),
                "cpu": cpu,
                # Memory
                "mem": mem_pct,  # legacy: percent
                "mem_pct": mem_pct,
                "mem_total_mb": mem_total_mb,
                "mem_used_mb": mem_used_mb,
                "mem_available_mb": mem_available_mb,
                # GPU
                "gpu": legacy_gpu,  # legacy: single util
                "gpu_mem": legacy_gpu_mem,  # legacy: single memory used (MB)
                "gpu_utils": gpu_utils,
                "gpu_mem_used_mb": gpu_mem_used,
                "gpu_mem_total_mb": gpu_mem_total,
                # Static info
                "server_info": self.server_info,
                "gpu_info": self.gpu_info,
                "gpu_available": self.gpu_available,
                "gpu_reason": self.gpu_reason,
            })
            time.sleep(self.interval)

    def stop(self):
        self.running = False
