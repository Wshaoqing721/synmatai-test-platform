BASE_URL = "http://192.168.1.9:19095"
WS_BASE_URL = "ws://192.168.1.9:19095"

AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzY5NDA5Nzg1LCJpYXQiOjE3Njg4MDQ5ODUsImp0aSI6IjcxMjk1NWJhY2EwNTQzYjE4NDlmOTlhNTdhMzM2YjJjIiwidXNlcl9pZCI6MX0.UfrsNrsiFeJRBvZU-JdQ3qsF9emheaTXdY_P-mHWwfM"
USER_ID = 19

# locust
LOCUST_USERS = 1
LOCUST_SPAWN_RATE = 1
LOCUST_RUN_TIME = "4h"

# monitor
SYSTEM_MONITOR_INTERVAL = 2.0

REPORT_PATH = "src/tests/reports/patent_test_report.json"
# =========================
# 终止阈值 / 保护策略
# =========================
# 内存保护：使用 available（更接近“还能分配的内存”）
MEM_AVAILABLE_MIN_GB = 10.0      # 硬阈值：低于 20GB 直接停
MEM_AVAILABLE_MIN_RATIO = 0.05   # 软阈值：低于 15% 直接停