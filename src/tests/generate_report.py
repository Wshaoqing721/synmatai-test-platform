import json
import sys
import os
from pathlib import Path

# Add src to sys.path
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from tests.reporter.report_writer import ReportWriter

def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <path_to_report.json>")
        print("Example: python src/tests/generate_report.py src/tests/reports/patent_test_report.json")
        return

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"❌ File not found: {json_path}")
        return

    print(f"📂 Reading JSON: {json_path}")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load JSON: {e}")
        return

    writer = ReportWriter()
    
    # Check if it is a ramp report or standard report
    if "ramp" in data:
        print("📊 Detecting Ramp Report format...")
        ramp_report = data["ramp"]
        # write_ramp_report expects the 'ramp' dict, not the root dict?
        # Let's check report_writer.py again.
        # Yes: def write_ramp_report(self, path, ramp_report: dict):
        writer.write_ramp_report(str(json_path), ramp_report)
    else:
        print("📊 Detecting Standard Report format...")
        # For standard report, ReportWriter.write() generates report from internal state usually.
        # However, _render_html(report) exists.
        # But ReportWriter.write(path) uses internal state.
        # So we might need to manually call _render_html if we want to regenerate from JSON purely.
        # But ReportWriter doesn't seem to have a 'generate_from_json' method for standard reports.
        # Assuming the user is interested in the ramp report for now based on context.
        print("⚠️  Standard report regeneration from JSON is not fully supported by this script yet.")

if __name__ == "__main__":
    main()
