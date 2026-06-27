# 本地模型文章翻译器 · Local Document Translator

[English](#english) | [中文](#中文)

一个跨平台桌面应用：用**本地大模型**把 PDF / Word / Markdown / 纯文本 / 图片翻译成中文。可连接 LM Studio，也可内置 llama.cpp 完全离线运行。

A cross-platform desktop app that translates **PDF / Word / Markdown / plain-text / images** into Chinese using local LLMs — via LM Studio, or fully offline with a bundled llama.cpp engine.

![icon](icon.png)

---

## 中文

### 功能
- 支持 **PDF / Word(.docx) / Markdown / 纯文本**，以及**图片 OCR**（先用 `glm-ocr` 识别再翻译）
- 原文 / 译文并排，逐段实时显示，加载或识别后**自动开始翻译**
- **Markdown 渲染**开关（标题/列表/加粗/表格），导出 PDF 保留格式
- 每个窗口可单独**调整字号**；支持**拖拽文件**进窗口
- 译文可微调后**导出 PDF / 文本**

### 两种后端
| 后端 | 说明 |
|------|------|
| **远程 (LM Studio)** | 连接任意 OpenAI 兼容服务，默认 `http://localhost:1234` |
| **本地 (llama.cpp)** | 内置 `llama-server`，无需外部服务，**完全离线** |

本地模式的模型由 `llama-server` 用 `-hf` **首次自动下载**到 `models/`，已存在则直接加载。下载源可在
**HuggingFace / 国内镜像(hf-mirror) / ModelScope** 间切换，`自动`模式会在 HuggingFace 不可达时自动改用镜像。

- 翻译模型：`tencent/Hy-MT2-1.8B-GGUF`（默认 Q4_K_M）
- OCR 模型：`ggml-org/GLM-OCR-GGUF`（含多模态 mmproj）

### 快速开始（源码运行）
```bash
git clone <your-repo-url>
cd Translator
pip install -r requirements.txt
python main.py
```

### 使用本地 llama.cpp（离线）
```bash
python setup_local.py        # 下载本机对应的 llama.cpp 引擎到 llama/
```
然后在应用顶部把「后端」切到 **本地 (llama.cpp)**，国内用户把「下载源」选 **国内镜像** 或 **ModelScope**。
首次会自动下载模型（翻译约 1GB，OCR 数 GB），之后秒开。

### 打包成 exe
```bash
pip install -r requirements-dev.txt
pyinstaller --noconfirm --windowed --name Translator --icon icon.ico \
  --add-data "icon.ico;." --add-data "icon.png;." --add-data "llama_config.json;." main.py
```
打 tag（`v*`）后，GitHub Actions 会自动构建 Windows 版并发布到 Releases。

### 配置
`llama_config.json` 可改：模型仓库、量化（`quant`）、端口、上下文长度、`-ngl`、下载源等。

---

## English

### Features
- **PDF / Word / Markdown / plain text** plus **image OCR** (recognised with `glm-ocr`, then translated)
- Side-by-side source/translation, streamed per paragraph, **auto-starts** after loading
- **Markdown rendering** toggle; PDF export keeps formatting
- Per-pane **font-size** controls; **drag-and-drop** files
- Export translation to **PDF / text**

### Backends
- **Remote (LM Studio)** — any OpenAI-compatible server, default `http://localhost:1234`
- **Local (llama.cpp)** — bundled `llama-server`, fully offline. Models auto-download via `-hf`
  with **HuggingFace / hf-mirror / ModelScope** fallback.

### Quick start
```bash
pip install -r requirements.txt
python main.py
# optional offline engine:
python setup_local.py
```

### Platforms
Code runs on **Windows / Linux / macOS**. Prebuilt binaries are provided for **Windows (x64)** and
**macOS (Apple Silicon / arm64)** under [Releases](../../releases). `setup_local.py` fetches the right
llama.cpp build per OS (Vulkan on Win/Linux, Metal on macOS). Models download on first use to a
per-user data dir (`%LOCALAPPDATA%\llamatrans` / `~/Library/Application Support/llamatrans`).

> **macOS**: the app is unsigned, so on first launch right-click the app → **Open** (or run
> `xattr -dr com.apple.quarantine Translator.app`) to bypass Gatekeeper.

---

## 许可证 · License
- 应用代码：**MIT**（见 [LICENSE](LICENSE)）
- AI 模型与 llama.cpp 二进制：各自遵循其原始许可证（Tencent Hy-MT2、GLM-OCR、llama.cpp 等）

## 文件说明 · Files
| 文件 | 作用 |
|------|------|
| `main.py` | 应用主程序与界面 |
| `extractors.py` | 从 PDF / Word / Markdown / 文本提取段落 |
| `translator.py` | 翻译 / OCR 客户端（OpenAI 兼容，按角色分端点）|
| `llama_backend.py` | 本地 llama.cpp 后端（多源下载、健康检查、分端口）|
| `llama_config.json` | 本地后端配置（模型仓库、量化、端口、下载源）|
| `setup_local.py` | 按操作系统下载 llama.cpp 引擎到 `llama/` |
| `convert_icon.py` / `make_icon.py` | 图标生成工具 |
