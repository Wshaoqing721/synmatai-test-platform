import json

def render_html(report, path):
    html = f"""
    <html>
    <head>
      <title>Nexus Load Test Report</title>
      <script src="https://cdn.jsdelivr.net/npm/echarts/dist/echarts.min.js"></script>
    </head>
    <body>
      <h1>Nexus 压测报告</h1>
      <pre>{json.dumps(report, indent=2)}</pre>
    </body>
    </html>
    """
    with open(path, "w") as f:
        f.write(html)
