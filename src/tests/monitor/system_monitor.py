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
            # Handle multiple GPUs (output may contain multiple lines)
            # Example output:
            # 0, 989
            # 52, 13442
            lines = out.strip().splitlines()
            if not lines:
                return None, None

            total_gpu = 0
            total_mem = 0
            count = 0

            for line in lines:
                if not line.strip():
                    continue
                parts = line.split(",")
                if len(parts) >= 2:
                    total_gpu += float(parts[0].strip())
                    total_mem += float(parts[1].strip())
                    count += 1
            
            if count > 0:
                # Return average GPU util and sum Memory used (or average memory? Usually total used is more relevant for OOM check, but average util for load)
                # Note: `system_metrics` in existing code seems to expect a single value.
                # Let's return the Max utilization of any GPU to see bottlenecks, or Average.
                # Average describes "system load". Max describes "bottleneck". 
                # Let's use Average validation for now to match simplicity.
                return int(total_gpu / count), int(total_mem / count) # Average Memory per GPU? Or Total? 
                
                # If we have 2 GPUs, 1 is 100%, 1 is 0%. Average is 50%.
                # If we return Avg, it's fine for general trend.
                
            return None, None
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
