# -*- coding: utf-8 -*-
"""
NeuroKey AGI yo'li — bitta buyruq bilan benchmark + ishga tushirish.

    python agi_runner.py                  # benchmark + hisobot
    python agi_runner.py --launch         # benchmark, keyin main.py
    python agi_runner.py --quick          # tez benchmark (LLM siz)
    python agi_runner.py --launch --skip-benchmark
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="NeuroKey AGI yo'li runner")
    parser.add_argument("--launch", action="store_true", help="Benchmarkdan keyin main.py")
    parser.add_argument("--quick", action="store_true", help="LLM chaqiruvisiz benchmark")
    parser.add_argument("--skip-benchmark", action="store_true", help="Faqat ishga tushirish")
    args = parser.parse_args()

    from boot_tier import apply_boot_tier
    from agi_config import apply_agi_config

    apply_boot_tier()
    apply_agi_config()

    print("\n[AGI-RUNNER] NeuroKey AGI yo'li — tekshiruv va ishga tushirish\n")

    if not args.skip_benchmark:
        from benchmark_20 import run_all
        code = run_all(quick=args.quick)
        if code != 0 and not args.launch:
            return code

    if args.launch:
        py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
        if not os.path.isfile(py):
            py = sys.executable
        main_py = os.path.join(ROOT, "main.py")
        print("\n[AGI-RUNNER] NeuroKey ishga tushmoqda (ovoz + mikrofon)...\n")
        print("  Yopish: Ctrl+C yoki !NeuroKey.bat stop\n")
        env = os.environ.copy()
        env.setdefault("NEUROKEY_ALLOW_UNLICENSED", "1")
        return subprocess.call([py, main_py], cwd=ROOT, env=env)

    print("\n[AGI-RUNNER] Benchmark tugadi. Ishga tushirish:")
    print("  !NeuroKey_AGI.bat")
    print("  yoki: python agi_runner.py --launch\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
