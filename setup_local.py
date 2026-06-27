"""Download the llama.cpp server engine for this OS into ./llama.

Optional convenience for running from source / CI. The app itself also
auto-downloads the engine (into a user-data dir) on first local-mode use.

Usage:  python setup_local.py
"""

from __future__ import annotations

import os
import sys

import engine

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def main():
    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llama")
    try:
        exe = engine.download_engine(dest, on_log=print)
    except engine.EngineError as e:
        print(f"\n失败: {e}")
        sys.exit(1)
    print("\n完成 ✓")
    print(f"llama-server: {exe}")
    print("现在在 App 中切换到「本地 (llama.cpp)」即可，首次使用会自动下载模型。")


if __name__ == "__main__":
    main()
