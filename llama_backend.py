"""Local llama.cpp backend manager.

Spawns one `llama-server` process per role (translation / OCR), each serving an
OpenAI-compatible API on its own local port. Models are auto-downloaded from
HuggingFace by llama-server itself (`-hf <repo>`) into a local cache folder, so
"present -> load, missing -> download" is handled natively.

The app then just points the Translator at the local ports instead of the
remote LM Studio server.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import requests


def app_dir() -> str:
    """Directory of the app (works in dev and inside a PyInstaller bundle)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _resource(name: str) -> str:
    """A bundled read-only resource (config shipped inside the bundle)."""
    base = getattr(sys, "_MEIPASS", app_dir())
    return os.path.join(base, name)


class LlamaBackendError(Exception):
    pass


class LlamaServer:
    """Handle to one running llama-server process for a single role."""

    def __init__(self, role: str, port: int, host: str, proc: subprocess.Popen):
        self.role = role
        self.port = port
        self.host = host
        self.proc = proc

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def is_alive(self) -> bool:
        return self.proc.poll() is None

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            except Exception:  # noqa: BLE001
                pass


class LlamaBackend:
    """Manages local llama-server processes described by llama_config.json."""

    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)
        self.base = app_dir()
        self.servers: dict[str, LlamaServer] = {}
        self._session = requests.Session()
        # "auto" | "huggingface" | "hf-mirror" | "modelscope"
        self.download_source = self.config.get("download_source", "auto")

    # -- config ---------------------------------------------------------

    def _load_config(self, config_path: str | None) -> dict:
        path = config_path or _resource("llama_config.json")
        if not os.path.exists(path):
            # fall back to a writable copy next to the app
            path = os.path.join(app_dir(), "llama_config.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _abs(self, rel: str) -> str:
        return rel if os.path.isabs(rel) else os.path.join(self.base, rel)

    @property
    def server_binary(self) -> str:
        rel = self.config.get("server_binary", "llama/llama-server")
        path = self._abs(rel)
        # add the platform-specific executable suffix if not already present
        if os.name == "nt" and not path.lower().endswith(".exe"):
            path += ".exe"
        return path

    @property
    def models_dir(self) -> str:
        return self._abs(self.config.get("models_dir", "models"))

    def role_cfg(self, role: str) -> dict:
        roles = self.config.get("roles", {})
        if role not in roles:
            raise LlamaBackendError(f"未知角色: {role}")
        return roles[role]

    # -- availability ---------------------------------------------------

    def binary_available(self) -> bool:
        return os.path.exists(self.server_binary)

    def base_url(self, role: str) -> str | None:
        srv = self.servers.get(role)
        return srv.base_url if srv and srv.is_alive() else None

    # -- lifecycle ------------------------------------------------------

    def _source_order(self) -> list[str]:
        """Resolve which download sources to try, in order."""
        if self.download_source != "auto":
            return [self.download_source]
        order = list(self.config.get(
            "auto_order", ["huggingface", "hf-mirror", "modelscope"]))
        # if huggingface.co is unreachable (e.g. in China), try mirrors first
        try:
            self._session.head("https://huggingface.co", timeout=5)
        except requests.RequestException:
            order = [s for s in order if s != "huggingface"] + \
                    (["huggingface"] if "huggingface" in order else [])
        return order

    def _repo_for(self, cfg: dict, source: str) -> str | None:
        """Repo id + quant tag for a given source, or None if unavailable."""
        repo = cfg.get("ms") if source == "modelscope" else cfg.get("hf")
        if not repo:
            return None
        quant = cfg.get("quant")
        return f"{repo}:{quant}" if quant else repo

    def start(self, role: str, on_log=None, ready_timeout: int = 1800) -> str:
        """Start (or reuse) the server for a role and return its base URL.

        Tries each configured download source until one succeeds. ready_timeout
        is generous because the first run may download several GB.
        """
        existing = self.servers.get(role)
        if existing and existing.is_alive():
            return existing.base_url

        if not self.binary_available():
            raise LlamaBackendError(
                f"未找到 llama-server，可执行文件应位于:\n{self.server_binary}\n"
                "请先运行 setup_local.py 下载本地引擎。"
            )

        cfg = self.role_cfg(role)
        os.makedirs(self.models_dir, exist_ok=True)
        endpoints = self.config.get("endpoints", {})

        errors = []
        for source in self._source_order():
            repo = self._repo_for(cfg, source)
            if not repo:
                continue  # this role has no repo for this source (e.g. OCR on MS)
            try:
                if on_log:
                    on_log(f"尝试下载源「{source}」: {repo}")
                return self._launch(role, cfg, repo, source, endpoints,
                                    ready_timeout, on_log)
            except LlamaBackendError as e:
                errors.append(f"[{source}] {e}")
                self.stop(role)
                if on_log:
                    on_log(f"下载源「{source}」失败，尝试下一个…")
        raise LlamaBackendError("所有下载源均失败:\n" + "\n".join(errors))

    def _launch(self, role, cfg, repo, source, endpoints, ready_timeout, on_log):
        port = int(cfg["port"])
        host = self.config.get("host", "127.0.0.1")
        cmd = [
            self.server_binary,
            "-hf", repo,
            "--host", host,
            "--port", str(port),
            "-ngl", str(self.config.get("ngl", 99)),
            "-c", str(cfg.get("ctx", 4096)),
            *cfg.get("extra", []),
        ]
        env = dict(os.environ)
        env["LLAMA_CACHE"] = self.models_dir  # download/cache GGUFs here
        endpoint = endpoints.get(source, "")
        if endpoint:
            env["MODEL_ENDPOINT"] = endpoint  # mirror / modelscope
        else:
            env.pop("MODEL_ENDPOINT", None)   # official HuggingFace

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW  # no console popup

        try:
            proc = subprocess.Popen(
                cmd, env=env, cwd=self.base,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=creationflags,
            )
        except OSError as e:
            raise LlamaBackendError(f"无法启动 llama-server: {e}") from e

        server = LlamaServer(role, port, host, proc)
        self.servers[role] = server
        self._wait_ready(server, ready_timeout, on_log)
        return server.base_url

    def _wait_ready(self, server: LlamaServer, timeout: int, on_log):
        """Poll the health endpoint until the model is loaded (or it dies)."""
        url = f"{server.base_url}/health"
        models_url = f"{server.base_url}/v1/models"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not server.is_alive():
                tail = self._drain_log(server)
                raise LlamaBackendError(
                    f"llama-server 进程已退出。最后输出:\n{tail}"
                )
            try:
                r = self._session.get(url, timeout=3)
                if r.status_code == 200:
                    try:
                        st = r.json().get("status")
                    except Exception:  # noqa: BLE001
                        st = "ok"
                    if st in (None, "ok"):
                        # confirm the OpenAI endpoint answers too
                        try:
                            if self._session.get(models_url, timeout=3).ok:
                                if on_log:
                                    on_log(f"{server.role} 服务就绪: {server.base_url}")
                                return
                        except requests.RequestException:
                            pass
            except requests.RequestException:
                pass
            time.sleep(1.0)
        raise LlamaBackendError(f"{server.role} 服务启动超时（{timeout}s）")

    def _drain_log(self, server: LlamaServer, limit: int = 4000) -> str:
        try:
            if server.proc.stdout:
                return server.proc.stdout.read()[-limit:]
        except Exception:  # noqa: BLE001
            pass
        return "(无输出)"

    def served_model_id(self, role: str) -> str | None:
        url = self.base_url(role)
        if not url:
            return None
        try:
            r = self._session.get(f"{url}/v1/models", timeout=5)
            data = r.json().get("data", [])
            return data[0]["id"] if data else None
        except (requests.RequestException, KeyError, IndexError):
            return None

    def stop(self, role: str):
        srv = self.servers.pop(role, None)
        if srv:
            srv.stop()

    def stop_all(self):
        for role in list(self.servers.keys()):
            self.stop(role)
