import time
import psutil
import subprocess
import shutil

class SystemMonitor:
    def __init__(self, interval=2):
        self.interval = interval
        self.running = False
        self.records = []

        self.gpu_available = bool(shutil.which("nvidia-smi"))
        self.gpu_reason = None if self.gpu_available else "nvidia-smi not found"

    def _gpu_usage(self):
        if not self.gpu_available:
            return None, None
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                 "--format=csv,noheader,nounits"],
                encoding="utf-8"
            )
            gpu, mem = out.strip().split(",")
            return int(gpu), int(mem)
        except Exception:
            return None, None

    def run(self):
        self.running = True
        while self.running:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            gpu, gpu_mem = self._gpu_usage()

            self.records.append({
                "ts": time.time(),
                "cpu": cpu,
                "mem": mem,
                "gpu": gpu,
                "gpu_mem": gpu_mem,
                "gpu_available": self.gpu_available,
                "gpu_reason": self.gpu_reason,
            })
            time.sleep(self.interval)

    def stop(self):
        self.running = False
