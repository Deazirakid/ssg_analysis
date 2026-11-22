"""Full pipeline: scrape ss.ge -> clean -> heatmap.html -> Excel dashboard.

    python run_all.py                 # full run (threads auto: 3 x logical cores, 30..64)
    python run_all.py --workers 32    # override threads
    python run_all.py --rebuild       # skip scraping, rebuild outputs from latest raw run
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "src"


def step(script, *args):
    print(f"\n=== {script} {' '.join(args)} ===", flush=True)
    subprocess.run([sys.executable, "-u", str(SRC / script), *args], check=True, cwd=ROOT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int)
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    if not a.rebuild:
        step("scrape.py", *(["--workers", str(a.workers)] if a.workers else []))
    step("clean.py")
    step("build_heatmap.py")
    step("build_excel.py")
    step("build_app_data.py")
    step("load_mysql.py")       # MariaDB = source of truth for the web app
    print("\nDone -> output/ss_ge_real_estate_dashboard.xlsx, output/heatmap.html, data/clean/*.csv")
