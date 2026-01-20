def render_md(report, path):
    lines = ["# Nexus 压测报告\n"]

    lines.append("## 任务统计\n")
    for tid, t in report["tasks"].items():
        statuses = t["status_timeline"]
        duration = statuses[-1]["ts"] - statuses[0]["ts"] if len(statuses) > 1 else 0
        lines.append(
            f"- {tid} | {t['task_type']} | {statuses[-1]['status']} | {duration:.2f}s"
        )

    lines.append("\n## 系统资源\n")
    if report["system_metrics"]:
        max_cpu = max(m["cpu"] for m in report["system_metrics"])
        max_mem = max(m["mem_mb"] for m in report["system_metrics"])
        lines.append(f"- CPU 峰值：{max_cpu}%")
        lines.append(f"- 内存峰值：{max_mem} MB")

    with open(path, "w") as f:
        f.write("\n".join(lines))
