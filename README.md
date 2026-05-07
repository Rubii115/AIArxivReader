# arxiv-reader

一个面向研究者的 AI arXiv 阅读助手。它的核心工作流是：

1. 先按 arXiv 分类和日期抓取候选论文。
2. 用题目和摘要判断是否符合你的研究兴趣。
3. 对你点开的论文下载 arXiv TeX 源码，让 AI 精读正文、公式和结构。
4. 在浏览器里继续追问这篇论文的细节。

这个项目默认面向 `quant-ph`，也就是量子物理方向；当前配置特别偏向超导量子计算实验、量子模拟、量子纠错、量子调控、多体物理、非厄密物理、量子信息和量子热力学等主题。

## 功能

- **今日论文筛选**：抓取指定日期的 `quant-ph` 新论文，先看标题和摘要，由 AI 判断哪些和你的兴趣相关。
- **源码级深读**：对单篇论文下载 arXiv source，抽取 TeX / bbl / sty / cls 文本，生成面向你的专业总结。
- **流式输出**：深读报告和后续问答都会在 Web UI 里流式显示。
- **临时论文会话**：每篇论文可以开启一个临时会话，基于同一份源码和首次总结继续追问。
- **历史筛选报告**：每次筛选会保存到 `runs/*.json`，之后可以在页面里选择任意历史报告重新打开。
- **出版物反查**：粘贴标题、作者、DOI、BibTeX 或索引条目，搜索可能对应的 arXiv 论文。
- **无 key 降级**：没有设置 API Key 时仍可跑通检索和源码解析，但总结会退化为本地摘要。

## 快速开始

下面以 Windows PowerShell 为例。

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

看到命令行前面出现 `(.venv)` 后，再继续安装和配置。

### 2. 安装项目

```powershell
python -m pip install -e .
Copy-Item config.example.toml config.toml
```

### 3. 在虚拟环境里设置 DeepSeek API Key

请先确认你仍然在 `(.venv)` 环境里，然后设置 key：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
$env:DEEPSEEK_MODEL="deepseek-v4-flash"
```

这两个 `$env:` 设置只对当前 PowerShell 窗口生效。以后重新开终端时，需要再次激活虚拟环境并重新设置 key。

也可以切到 OpenAI 兼容模式：

```powershell
$env:AI_PROVIDER="openai"
$env:OPENAI_API_KEY="你的 OpenAI API Key"
$env:OPENAI_MODEL="gpt-4.1-mini"
```

### 4. 启动 Web UI

```powershell
arxiv-reader-web --host 127.0.0.1 --port 8765
```

然后打开：

[http://127.0.0.1:8765](http://127.0.0.1:8765)

## 推荐使用方式

### 筛选今日论文

在 Web UI 的“筛选”页：

1. 选择日期。
2. 设置“初筛候选数”，默认来自 `config.toml` 的 `candidate_count`。
3. 检查或修改“兴趣描述”。
4. 点击“阅读今日论文”。

筛选时会持续显示进度，包括：

- 正在请求哪一天的 arXiv。
- 抓取到了多少篇候选论文。
- 正在分析哪篇论文的相关性。
- 哪些论文被判定为相关。
- 报告保存到了哪个 `runs/*.json`。

筛选完成后，页面默认展示所有被 AI 判定为相关的论文。你也可以点击“显示全部候选”查看没入选的论文和理由。

### 深读单篇论文

在“单篇”页输入 arXiv ID 或 URL，例如：

```text
2605.04049
https://arxiv.org/abs/2605.04049
```

点击“深读并开启会话”后，程序会：

1. 获取论文元数据。
2. 下载 arXiv TeX 源码。
3. 抽取主要 TeX 文本。
4. 流式生成首次总结。
5. 打开一个可以继续追问的论文会话。

### 读取历史筛选报告

每次筛选都会保存一个 JSON 文件到 `runs/`，例如：

```text
runs/20260507-042521-9cc57b99.json
```

在“筛选”页的“历史筛选报告”下拉框里，可以选择任意历史报告并点击“加载选中报告”。这适合你先筛出一批论文，读完其中一两篇后再回到同一批列表继续看。

## 命令行用法

Web UI 是主要入口，但也保留了 CLI。

总结单篇论文：

```powershell
arxiv-reader summarize 2401.00001
```

按配置筛选并总结某天论文：

```powershell
arxiv-reader today --config config.toml --date 2026-05-07 --limit 5
```

用出版物索引信息反查 arXiv：

```powershell
arxiv-reader find "Attention Is All You Need Vaswani 2017"
```

也可以传入 BibTeX、Crossref 文本或 DBLP 条目：

```powershell
arxiv-reader find "@article{..., title={...}, author={...}, doi={...}}"
```

## 配置

主要配置在 [config.example.toml](config.example.toml)。复制成 `config.toml` 后按自己的方向修改。

```toml
[interests]
categories = ["quant-ph"]
keywords = ["quantum simulation", "quantum error correction"]
explain_for = """
这里写长期兴趣描述。
"""

[reading]
max_source_chars = 120000
max_papers_per_run = 10
candidate_count = 60
```

字段含义：

- `categories`：arXiv 分类。量子物理默认是 `quant-ph`。
- `keywords`：命令行检索时会拼进查询条件；Web UI 的今日筛选主要按分类和日期抓候选，再交给 AI 判断相关性。
- `explain_for`：长期提示词。告诉 AI 你是谁、你关心什么、什么样的论文值得读。
- `max_source_chars`：每篇论文最多送入模型的源码字符数。`120000` 大约是数万英文词，通常足够覆盖主 TeX、参考文献片段和关键宏定义。
- `max_papers_per_run`：CLI `today` 的默认处理篇数；Web UI 当前不再用它限制入选论文数量。
- `candidate_count`：Web UI 每次从 arXiv 抓取多少篇候选论文做标题/摘要初筛。

## 推荐提示词

可以把下面这段放进 `config.toml` 的 `explain_for`：

```text
我是超导量子计算实验方向的研究者。请把论文按“是否值得我进一步读”来筛选，而不是只按标题是否包含热门词。

我关注超导量子计算实验、量子模拟、量子纠错、量子调控、量子测量、开放量子系统、噪声建模和实验可观测量。只要论文能启发超导量子平台探索量子物理热点问题，即使不是直接用超导体系，也应当给出较高关注。

我也对有清晰物理机制或新量子图像的理论模型感兴趣，包括多体物理、非厄密物理、量子信息、量子热力学、拓扑现象和动力学相变。请特别关注论文是否提出具体 Hamiltonian、动力学机制、控制方法、误差模型、可观测量或可实验验证的预测。

判断相关性时请区分“标题很 fancy”与“真正有工作点”。优先保留有明确物理问题、可复现实验/理论框架、可能影响量子平台设计或解释实验现象的论文。
```

## 项目结构

```text
src/arxiv_reader/
  ai.py              AI 调用、流式总结、本地降级摘要
  arxiv.py           arXiv API 检索、论文元数据、源码下载
  cli.py             命令行入口
  config.py          TOML 配置加载
  publication.py     出版物索引文本解析与查询生成
  static/index.html  Web 前端
  tex.py             TeX 源码抽取与拼接
  web.py             Web 服务和 JSON/SSE API
tests/
```

## 常见问题

### 为什么页面说没有读取到 API Key？

最常见原因是：你在一个 PowerShell 窗口里设置了 `$env:DEEPSEEK_API_KEY`，但 Web 服务是在另一个窗口启动的。请在启动服务的同一个窗口里执行：

```powershell
.\.venv\Scripts\Activate.ps1
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
arxiv-reader-web --host 127.0.0.1 --port 8765
```

### 为什么要先按标题摘要筛选，再读 TeX 源码？

每天 `quant-ph` 新论文可能有几十篇。先用标题和摘要做便宜的相关性判断，可以避免把每篇论文源码都下载并送入模型；只有你真正想看的论文才进入源码级深读。

### 如果 arXiv source 里有多个 TeX 文件怎么办？

程序会收集源码包里的多个 `.tex` 文件，并优先让主文件和正文内容进入上下文；同时也会保留 `.bbl`、`.sty`、`.cls` 的部分内容，直到达到 `max_source_chars` 限制。

### 历史报告会一直保存吗？

会保存到本地 `runs/` 目录。这个目录已经加入 `.gitignore`，不会被提交到代码仓库。需要清理时可以手动删除旧 JSON。
