"""Download the llama.cpp server binary for this OS into ./llama.

Picks the right prebuilt release asset for Windows / Linux / macOS, extracts it,
and verifies the llama-server executable is present. Models are NOT downloaded
here — the app downloads them on first use via llama-server's `-hf` mechanism
(with HuggingFace / hf-mirror / ModelScope fallback).

Usage:  python setup_local.py
"""

from __future__ import annotations

import io
import os
import platform
import sys
import zipfile
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HERE, "llama")
API_LATEST = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
# mirrors prepended to download URLs if the direct download fails (e.g. in China)
DL_MIRRORS = ["", "https://ghfast.top/", "https://mirror.ghproxy.com/"]
EXE = "llama-server.exe" if os.name == "nt" else "llama-server"


def _platform_keywords() -> list[str]:
    """Substrings (lowercase) an asset name should contain for this platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if system == "windows":
        # Vulkan build runs on NVIDIA/AMD/Intel GPUs
        return ["win", "vulkan", "x64"]
    if system == "darwin":
        return ["macos", "arm64" if arm else "x64"]
    # linux
    return ["ubuntu", "vulkan", "x64"]


def _score_asset(name: str, keywords: list[str]) -> int:
    name = name.lower()
    if not name.endswith(".zip"):
        return -1
    return sum(1 for k in keywords if k in name)


def _find_asset(assets: list[dict]) -> dict | None:
    keywords = _platform_keywords()
    best, best_score = None, 0
    for a in assets:
        score = _score_asset(a.get("name", ""), keywords)
        if score > best_score:
            best, best_score = a, score
    # require at least the OS keyword to match
    if best and best_score >= 1:
        return best
    # loose fallback: any zip mentioning the OS keyword
    os_kw = keywords[0]
    for a in assets:
        if a.get("name", "").lower().endswith(".zip") and os_kw in a["name"].lower():
            return a
    return None


def main():
    print(f"平台: {platform.system()} {platform.machine()}")
    print("查询 llama.cpp 最新发行版…")
    r = requests.get(API_LATEST, timeout=30,
                     headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    release = r.json()
    tag = release.get("tag_name", "?")
    asset = _find_asset(release.get("assets", []))
    if not asset:
        print("未找到适合本平台的预编译包，请手动下载：")
        print("  https://github.com/ggml-org/llama.cpp/releases/latest")
        sys.exit(1)

    print(f"版本 {tag}")
    print(f"下载 {asset['name']} ({asset.get('size', 0) / 1e6:.1f} MB)…")
    data = _download_with_mirrors(asset["browser_download_url"])

    os.makedirs(DEST, exist_ok=True)
    print(f"解压到 {DEST} …")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(DEST)

    exe = _locate(DEST, EXE)
    if not exe:
        print(f"解压完成，但未找到 {EXE}，请检查压缩包结构。")
        sys.exit(1)

    # flatten if the binary is nested in a subfolder
    exe_dir = os.path.dirname(exe)
    if os.path.normpath(exe_dir) != os.path.normpath(DEST):
        print("整理目录结构…")
        for item in os.listdir(exe_dir):
            dst = os.path.join(DEST, item)
            if not os.path.exists(dst):
                os.replace(os.path.join(exe_dir, item), dst)
        exe = os.path.join(DEST, EXE)

    if os.name != "nt":
        try:
            os.chmod(exe, 0o755)
        except OSError:
            pass

    print("\n完成 ✓")
    print(f"llama-server: {exe}")
    print("现在在 App 中切换到「本地 (llama.cpp)」即可，首次使用会自动下载模型。")


def _download_with_mirrors(url: str) -> bytes:
    last_err = None
    for prefix in DL_MIRRORS:
        full = f"{prefix}{url}" if prefix else url
        try:
            if prefix:
                print(f"  通过镜像重试: {prefix}")
            return _download(full)
        except requests.RequestException as e:
            last_err = e
            print(f"  下载失败: {e}")
    raise SystemExit(f"所有下载源均失败: {last_err}")


def _download(url: str) -> bytes:
    buf = io.BytesIO()
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        done = 0
        for chunk in resp.iter_content(chunk_size=1 << 20):
            buf.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                print(f"\r  {pct:3d}%  ({done/1e6:.0f}/{total/1e6:.0f} MB)",
                      end="", flush=True)
    print()
    return buf.getvalue()


def _locate(root: str, filename: str) -> str | None:
    for dirpath, _dirs, files in os.walk(root):
        if filename in files:
            return os.path.join(dirpath, filename)
    return None


if __name__ == "__main__":
    main()
