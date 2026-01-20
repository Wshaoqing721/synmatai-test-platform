import json
import sys
import os
from pathlib import Path

# Add src to sys.path to allow imports from tests.*
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from tests.reporter.report_writer import ReportWriter

def main():
    # Default path or get from argument
    default_path = current_dir / "reports" / "patent_test_report.json"
    
    if len(sys.argv) > 1:
        json_file = Path(sys.argv[1])
    else:
        json_file = default_path

    if not json_file.exists():
        print(f"❌ File not found: {json_file}")
        print(f"Usage: python {sys.argv[0]} [path/to/report.json]")
        return

    print(f"📂 Reading JSON: {json_file}")
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load JSON: {e}")
        return

    # Check for 'ramp' key (standard ramp report structure)
    if "ramp" in data:
        print("Creating Ramp Report...")
        ramp_report = data["ramp"]
        writer = ReportWriter()
        # This will write both .json and .html
        writer.write_ramp_report(str(json_file), ramp_report)
    else:
        # Fallback/Check if it's a standard task report
        # ReportWriter.write takes 'path' but expects internals to be set or tasks passed differently.
        # But ReportWriter.write() uses self.ws_monitor etc or local vars?
        # Let's look at write():
        # def write(self, path): ... task_table = self.build_task_table(tasks) ...
        # It relies on existing data in the class instance OR maybe I missed something.
        # But the user specifically asked for "this json file" which IS a ramp report (see attachments).
        print("⚠️  'ramp' key not found in JSON. Treating as standard report not fully supported by this simple script without task reconstruction logic.")
        return

if __name__ == "__main__":
    main()
