#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyPhi Python 3.10+ fix. pip install pyphi dan keyin ishga tushiring.

collections.Iterable -> collections.abc.Iterable (Python 3.10+ da o'zgargan).
"""
import os
import sys

def main():
    try:
        import pyphi
        pkg_dir = os.path.dirname(pyphi.__file__)
        db_path = os.path.join(pkg_dir, "db.py")
    except ImportError:
        print("PyPhi o'rnatilmagan. Avval: pip install pyphi")
        return 1

    if not os.path.isfile(db_path):
        print(f"db.py topilmadi: {db_path}")
        return 1

    with open(db_path, "r", encoding="utf-8") as f:
        content = f.read()

    if "collections.abc" in content:
        print("PyPhi allaqachon tuzatilgan.")
        return 0

    old = "from collections import Iterable"
    new = "try:\n    from collections import Iterable\nexcept ImportError:\n    from collections.abc import Iterable"

    if old not in content:
        print("db.py da expected qator topilmadi.")
        return 1

    content = content.replace(old, new)
    with open(db_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Tuzatildi: {db_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
