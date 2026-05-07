# AIArxivReader

## 一键安装和启动

Windows 用户可以直接使用两个批处理脚本：

1. 双击 `install.bat`：创建虚拟环境、安装项目，并生成 `config.toml` 和 `.env`。
2. 打开 `.env`，把 `DEEPSEEK_API_KEY` 改成你的真实 DeepSeek API Key。
3. 双击 `start.bat`：自动激活虚拟环境、打开浏览器并启动 Web UI。

默认地址是：

[http://127.0.0.1:8765](http://127.0.0.1:8765)

`.env` 和 `config.toml` 都是本地文件，已经在 `.gitignore` 里，不会上传到 GitHub。

一个面向量子物理研究者的 AI arXiv 阅读助手。它会先用题目和摘要筛选每日 `quant-ph` 新论文，再对你点开的论文下载 arXiv TeX 源码，让模型精读正文、公式和结构，最后在 Web UI 里继续追问。

## 主要功能

- 今日论文筛选：按日期抓取 `quant-ph` 候选论文，用你的兴趣描述做标题/摘要相关性判断。
- 源码级深读：下载 arXiv source，抽取 TeX / bbl / sty / cls 文本后生成专业总结。
- 流式输出：首次总结和后续问答都会在页面里逐步显示。
- 临时论文会话：打开任意论文后可以基于同一份源码继续追问。
- 历史报告：筛选结果保存到 `runs/*.json`，可以在页面里选择任意历史报告重新打开。
- 出版物反查：用标题、作者、DOI、BibTeX 或索引文本搜索对应 arXiv 论文。

## 快速开始

以下命令以 Windows PowerShell 为例。

### 1. 创建并激活虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

如果 PowerShell 阻止激活脚本，可以只对当前窗口放宽策略：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 2. 安装项目

```powershell
python -m pip install -e .
Copy-Item config.example.toml config.toml
```

### 3. 配置长期 API Key

推荐用本地 `.env` 文件，这样以后重新打开终端不需要反复设置 `$env:DEEPSEEK_API_KEY`。

```powershell
Copy-Item .env.example .env
notepad .env
```

把 `.env` 里的这一行改成你的真实 key：

```text
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_MODEL=deepseek-v4-flash
```

`.env` 已经写进 `.gitignore`，不会上传到 GitHub。以后只需要激活虚拟环境并启动服务，程序会自动读取 `.env`。

也可以临时用环境变量覆盖 `.env`：

```powershell
$env:DEEPSEEK_API_KEY="临时 key"
```

### 4. 启动 Web UI

```powershell
arxiv-reader-web --host 127.0.0.1 --port 8765
```

打开：

[http://127.0.0.1:8765](http://127.0.0.1:8765)

## 配置兴趣

长期研究兴趣放在 `config.toml` 的 `explain_for`。默认示例面向超导量子计算实验，同时保留对有趣理论模型的关注：

```toml
[interests]
categories = ["quant-ph"]
keywords = ["quantum simulation", "quantum error correction"]
explain_for = """
我是超导量子计算实验方向的研究者。请把论文按“是否值得我进一步读”来筛选。
"""
```

常用字段：

- `categories`：arXiv 分类，量子物理默认是 `quant-ph`。
- `keywords`：CLI 检索时会使用；Web UI 的每日筛选主要先按分类和日期抓候选，再交给 AI 判断。
- `explain_for`：你的长期提示词。
- `max_source_chars`：每篇论文最多送入模型的源码字符数。
- `candidate_count`：Web UI 每次抓取候选论文的安全上限。默认是 120；如果 arXiv 返回的当天总数超过这个上限，页面会提示还有多少篇没有筛到。

## 使用方式

### 今日筛选

在“筛选”页选择日期，确认兴趣描述，然后点击“阅读今日论文”。页面会持续显示进度：arXiv 当天共有多少候选、实际抓取了多少、正在分析哪篇、哪些论文被判定为相关，以及报告保存路径。

筛选完成后可以切换“显示相关论文”和“显示全部候选”。

### 单篇深读

在“单篇”页输入 arXiv ID 或 URL：

```text
2605.04049
https://arxiv.org/abs/2605.04049
```

点击“深读并开启会话”后，会下载源码、流式生成总结，并打开追问框。

### 历史报告

每次筛选都会保存一个 JSON 到 `runs/`。在“筛选”页的“历史筛选报告”下拉框中选择任意一次结果，再点“加载选中报告”即可。

## 命令行

总结单篇论文：

```powershell
arxiv-reader summarize 2401.00001
```

按配置筛选某天论文：

```powershell
arxiv-reader today --config config.toml --date 2026-05-07 --limit 5
```

用出版物索引信息反查 arXiv：

```powershell
arxiv-reader find "Attention Is All You Need Vaswani 2017"
```

## 常见问题

### 为什么页面说没有读取到 API Key？

请确认项目根目录有 `.env` 文件，并且内容类似：

```text
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-v4-flash
```

然后重启 `arxiv-reader-web`。服务启动时会读取 `.env`，运行中修改 `.env` 需要重启服务才生效。

### `.env` 会不会被上传？

不会。`.env` 已经在 `.gitignore` 里。仓库只提供 `.env.example` 作为模板。

### 为什么要先筛选再读源码？

每天 `quant-ph` 新论文可能有几十篇。先用标题和摘要做便宜的相关性判断，可以避免把每篇论文源码都下载并送进模型；只有你真正想看的论文才进入源码级深读。

## 项目结构

```text
src/arxiv_reader/
  ai.py              AI 调用、流式总结、本地降级摘要
  arxiv.py           arXiv API 检索、源码下载
  cli.py             命令行入口
  config.py          TOML 配置加载
  env.py             .env 文件加载
  publication.py     出版物索引文本解析
  static/index.html  Web 前端
  tex.py             TeX 源码抽取
  web.py             Web 服务和 JSON/SSE API
tests/
```
