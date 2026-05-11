# 🏭 MiMo Content Factory

> 基于小米 MiMo 多模型协同的自媒体内容工厂 —— 从选题到配音，56 秒出片。

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MiMo Token Plan](https://img.shields.io/badge/Model-MiMo_V2.5-orange.svg)](https://xiaomimimo.com)

---

## 这是什么

一个人做短视频，从选题 → 写脚本 → 录音频 → 找素材 → 剪视频，大半天就没了，产出还不稳定。

**MiMo Content Factory** 把这个流程拆成 3 个专门的 AI Agent，用小米 MiMo 系列模型驱动：

| 指标 | 人工 | Agent 管线 |
|------|------|-----------|
| 单条视频耗时 | 2-4 小时 | **56 秒** |
| 日产量 | 1-2 条 | 50+ 条 |
| 质量一致性 | 不稳定 | 审稿闭环保障 |

这不是简单的 prompt chain —— 每个 Agent 独立思考、独立执行，有状态管理、异常处理、质量评审闭环。

---

## 架构

```
┌──────────────────────────────────────────────────────────────────┐
│                     MiMo Content Factory                         │
│            调度 · 状态管理 · 异常处理 · 质量闭环                    │
├──────────────┬──────────────┬──────────────┬─────────────────────┤
│   Step 1     │   Step 2     │   Step 3     │      Step 4         │
│  编剧 Agent  │  配音 Agent  │  审稿 Agent  │     合并输出         │
│ MiMo-V2.5-Pro│ MiMo-V2.5-TTS│  MiMo-V2.5  │      ffmpeg         │
├──────────────┼──────────────┼──────────────┼─────────────────────┤
│  脚本 JSON   │  .wav 音频   │  评分+建议   │   完整配音文件       │
└──────────────┴──────────────┴──────────────┴─────────────────────┘
```

### 模型分工

| Agent | 模型 | 职责 | 能力 |
|-------|------|------|------|
| 编剧 | MiMo-V2.5-Pro | 脚本创作、分镜拆解、视频提示词 | 1M 上下文、深度推理 |
| 配音 | MiMo-V2.5-TTS | 语音合成、情绪控制 | 8 种音色、情绪标注、唱歌 |
| 审稿 | MiMo-V2.5 | 质量评分、内容审核、改进建议 | 5 维度评审、闭环反馈 |

---

## 实际效果

### 🥭 案例：芒果椰椰冰

**选题**：夏日芒果椰椰冰饮品推广

**编剧 Agent 输出**（21.8s / 1,606 tokens）：

```json
{
  "title": "一口就爱上！这杯芒果椰椰冰太夏天了",
  "shots": [
    {"narration": "夏天，就该有这一口。", "duration": 6, "emotion": "温暖、期待"},
    {"narration": "大块芒果肉，这用料太实在了。", "duration": 7, "emotion": "欢快、自信"},
    {"narration": "绵密冰沙，裹着果肉香。", "duration": 7, "emotion": "沉稳、满足"},
    {"narration": "喝到它，瞬间就凉快了。", "duration": 6, "emotion": "惊喜、治愈"}
  ]
}
```

**审稿 Agent 评分**（8.0s / 1,663 tokens）：

| 维度 | 分数 |
|------|------|
| 吸引力 | 9/10 |
| 口语感 | 9/10 |
| 节奏感 | 8/10 |
| 食欲感 | 9/10 |
| 一致性 | 9/10 |
| **总分** | **8.8/10** |

**性能统计**：

| 指标 | 数据 |
|------|------|
| 总耗时 | 56.2 秒 |
| 编剧 Agent | 21.8s / 1,606 tokens |
| 配音 Agent | 26.1s / 4 段音频 (442KB) |
| 审稿 Agent | 8.0s / 1,663 tokens |
| 合并输出 | 0.2s |

### 更多案例

- 🍧 **杨枝甘露** — `examples/yangzhiganlu.json`
- 🍮 **双皮奶** — `examples/shuangpinai.json`

---

## 快速开始

### 1. 环境准备

```bash
# Python 3.10+
python3 -m venv venv
source venv/bin/activate
pip install openai

# ffmpeg（音频合并）
sudo apt install ffmpeg  # Ubuntu/Debian
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env 填入你的 MiMo Token Plan API Key
```

### 3. 配置 TTS

```bash
# 安装 MiMo TTS 脚本
git clone https://github.com/XiaoMi/MiMo.git ~/MiMo-Skills
```

### 4. 运行

```bash
export MIMO_API_KEY=你的key

# 三模型管线（推荐）
python3 scripts/demo_pipeline.py --topic "芒果椰椰冰 — 夏日必喝" --voice "冰糖"

# 带额外上下文
python3 scripts/demo_pipeline.py --topic "双皮奶" --voice "冰糖" \
  --extra-context "湛江传统甜品，老字号"
```

### 5. 查看产出

```bash
ls /tmp/mimo-demo-*/
# script.json        — 脚本结构化数据
# shot_1.wav ~ 4.wav — 各镜头配音
# review.json        — 审稿评分
# stats.json         — 性能统计
# run_log.txt        — 完整运行日志
# full_voiceover.wav — 合并后的完整配音
```

---

## 技术亮点

### 1. 宽容 JSON 解析

LLM 输出的 JSON 经常格式不统一（中英文字段混用、代码块包裹、可能被截断）。解析器支持：
- 自动去除 markdown 代码块
- 正则提取 JSON 主体
- 容忍字段名变体

### 2. 情绪驱动配音

编剧 Agent 为每个镜头标注情绪（"温暖""欢快""沉稳""惊喜"），配音 Agent 将情绪注入 TTS 的 context 参数，让同一音色在不同镜头呈现不同情感。

### 3. 质量评审闭环

审稿 Agent 从 5 个维度评分，如果总分低于阈值可以自动触发重写。

### 4. 模块化 Agent 架构

每个 Agent 是独立函数，可以单独调用、替换、扩展。要换编剧模型？改 `agent_scriptwriter` 里的 `model` 参数就行。

---

## 扩展方向

- [ ] **联网搜索 Agent** — 自动搜索行业热点，智能选题
- [ ] **视频生成集成** — 对接 Seedance/Pika/Sora，自动生成视频画面
- [ ] **批量生产模式** — 一次输入多个选题，批量生成
- [ ] **平台发布集成** — 自动适配抖音/快手/B站的格式和标题
- [ ] **数据反馈闭环** — 根据视频播放数据优化脚本策略

---

## 项目结构

```
mimo-content-pipeline/
├── README.md                    # 本文档
├── requirements.txt             # Python 依赖
├── setup.py                     # 包安装
├── .env.example                 # 配置模板
├── LICENSE                      # MIT
├── docs/
│   ├── architecture.md          # 架构详解
│   └── performance.md           # 性能数据
├── examples/
│   ├── sample_script.json       # 芒果椰椰冰案例
│   ├── yangzhiganlu.json        # 杨枝甘露案例
│   └── shuangpinai.json         # 双皮奶案例
├── scripts/
│   ├── demo_pipeline.py         # 演示管线（推荐）
│   ├── multi_agent_pipeline.py  # 三模型管线
│   └── video_pipeline.py        # 四模型管线（含视频）
└── mimo_factory/                # Python 包（开发中）
```

---

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| LLM | MiMo-V2.5-Pro / MiMo-V2.5 | 小米 Token Plan API |
| TTS | MiMo-V2.5-TTS | 8 种音色、情绪控制 |
| 音频 | ffmpeg | 音频合并与处理 |
| 调度 | Python pipeline | 状态管理、异常处理 |

---

## License

MIT
