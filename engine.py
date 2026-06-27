"""Locate / download the llama.cpp server engine.

Shared by setup_local.py (CLI) and llama_backend.py (in-app auto-download).
Windows/Linux pull a prebuilt release from GitHub; macOS has no prebuilt
server in llama.cpp releases, so it must be built from source or bundled.
"""

from __future__ import annotations

import io
import os
import platform
import zipfile
import requests


API_LATEST = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
# mirrors prepended to download URLs if the direct download fails (e.g. China)
DL_MIRRORS = ["", "https://ghfast.top/", "https://mirror.ghproxy.com/"]


class EngineError(Exception):
    pass


def exe_name() -> str:
    return "llama-server.exe" if os.name == "nt" else "llama-server"


def platform_keywords() -> list[str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if system == "windows":
        return ["win", "vulkan", "x64"]      # GPU build, broad support
    if system == "darwin":
        return ["macos", "arm64" if arm else "x64"]
    return ["ubuntu", "vulkan", "x64"]       # linux


def find_asset(assets: list[dict]) -> dict | None:
    keywords = platform_keywords()
    best, best_score = None, 0
    for a in assets:
        name = a.get("name", "").lower()
        if not name.endswith(".zip") or "xcframework" in name:
            continue
        score = sum(1 for k in keywords if k in name)
        if score > best_score:
            best, best_score = a, score
    return best if best and best_score >= 1 else None


def locate(root: str, filename: str) -> str | None:
    for dirpath, _dirs, files in os.walk(root):
        if filename in files:
            return os.path.join(dirpath, filename)
    return None


def download_engine(dest_dir: str, on_log=print) -> str:
    """Download + extract the llama.cpp engine into dest_dir. Returns the
    llama-server path. Raises EngineError if no prebuilt exists for this OS."""
    on_log("查询 llama.cpp 最新发行版…")
    r = requests.get(API_LATEST, timeout=30,
                     headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    release = r.json()
    asset = find_asset(release.get("assets", []))
    if not asset:
        raise EngineError(
            f"llama.cpp 最新版未提供适用于 {platform.system()} 的预编译引擎。\n"
            "macOS 需从源码编译（或用 `brew install llama.cpp`）后放入 llama/。"
        )

    on_log(f"下载引擎 {asset['name']} ({asset.get('size', 0)/1e6:.0f} MB)…")
    data = _download_with_mirrors(asset["browser_download_url"], on_log)

    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(dest_dir)

    exe = locate(dest_dir, exe_name())
    if not exe:
        raise EngineError(f"解压后未找到 {exe_name()}")

    # flatten if nested in a subfolder
    exe_dir = os.path.dirname(exe)
    if os.path.normpath(exe_dir) != os.path.normpath(dest_dir):
        for item in os.listdir(exe_dir):
            dst = os.path.join(dest_dir, item)
            if not os.path.exists(dst):
                os.replace(os.path.join(exe_dir, item), dst)
        exe = os.path.join(dest_dir, exe_name())

    if os.name != "nt":
        try:
            os.chmod(exe, 0o755)
        except OSError:
            pass
    on_log(f"引擎就绪: {exe}")
    return exe


def _download_with_mirrors(url: str, on_log) -> bytes:
    last_err = None
    for prefix in DL_MIRRORS:
        full = f"{prefix}{url}" if prefix else url
        try:
            if prefix:
                on_log(f"通过镜像重试: {prefix}")
            return _download(full, on_log)
        except requests.RequestException as e:
            last_err = e
    raise EngineError(f"引擎下载失败: {last_err}")


def _download(url: str, on_log) -> bytes:
    buf = io.BytesIO()
    with requests.get(url, stream=True, timeout=180) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        done = 0
        last_pct = -1
        for chunk in resp.iter_content(chunk_size=1 << 20):
            buf.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                if pct != last_pct and pct % 5 == 0:
                    on_log(f"下载引擎 {pct}% ({done/1e6:.0f}/{total/1e6:.0f} MB)")
                    last_pct = pct
    return buf.getvalue()
