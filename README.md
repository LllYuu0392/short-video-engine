# 🏭 MiMo Content Factory

> 基于小米 MiMo 多模型协同的自媒体内容工厂 —— 从选题到配音到视频，5分钟出片。

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MiMo Token Plan](https://img.shields.io/badge/Model-MiMo_V2.5-orange.svg)](https://xiaomimimo.com)

---

## 这是什么

一个人做短视频，从选题 → 写脚本 → 录音频 → 找素材 → 剪视频，大半天就没了，产出还不稳定。

**MiMo Content Factory** 把这个流程拆成 4 个专门的 AI Agent，用小米 MiMo 系列模型 + 火山引擎 Seedance 驱动：

| 指标 | 人工 | Agent 管线 |
|------|------|-----------|
| 单条视频耗时 | 2-4 小时 | **~5 分钟** |
| 日产量 | 1-2 条 | 30+ 条 |
| 质量一致性 | 不稳定 | 审稿闭环保障 |

---

## 架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                       MiMo Content Factory                           │
│              调度 · 状态管理 · 异常处理 · 质量闭环                      │
├──────────────┬──────────────┬──────────────┬─────────────┬───────────┤
│   Step 1     │   Step 2     │   Step 3     │   Step 4    │  Step 5   │
│  编剧 Agent  │  配音 Agent  │  视频 Agent  │  审稿 Agent │  合并输出  │
│ MiMo-V2.5-Pro│ MiMo-V2.5-TTS│  Seedance    │  MiMo-V2.5  │  ffmpeg   │
│              │              │  1.5 Pro     │             │           │
├──────────────┼──────────────┼──────────────┼─────────────┼───────────┤
│  脚本 JSON   │  .wav 音频   │  .mp4 视频   │  评分+建议  │  最终视频  │
└──────────────┴──────────────┴──────────────┴─────────────┴───────────┘
```

### 模型分工

| Agent | 模型 | 职责 | API |
|-------|------|------|-----|
| 编剧 | MiMo-V2.5-Pro | 脚本创作、分镜拆解、视频提示词 | MiMo Token Plan |
| 配音 | MiMo-V2.5-TTS | 语音合成、情绪控制 | MiMo Token Plan |
| 视频 | Seedance 1.5 Pro | 文生视频（竖屏9:16，含音频） | 火山引擎方舟 |
| 审稿 | MiMo-V2.5 | 质量评分、内容审核 | MiMo Token Plan |

---

## 实际效果

### 🥭 案例：芒果椰椰冰

**选题**：夏日芒果椰椰冰饮品推广

**编剧 Agent 输出**（基于联网搜索的真实产品信息）：

```json
{
  "title": "三层热带风暴｜一口喝到夏天！",
  "shots": [
    {"narration": "满杯果肉打底，还有爆爆珠惊喜！", "duration": 7, "emotion": "惊喜、期待"},
    {"narration": "椰乳慢悠悠地漫上来，太治愈了！", "duration": 6, "emotion": "舒缓、治愈"},
    {"narration": "看这金黄沙冰盖上去！绝美分层！", "duration": 8, "emotion": "兴奋、惊叹"},
    {"narration": "三层喝到底，每一口都超满足！", "duration": 9, "emotion": "满足、强烈推荐"}
  ]
}
```

**视频生成**（Seedance 1.5 Pro，每段 8 秒）：

| 镜头 | 内容 | 时长 | 大小 |
|------|------|------|------|
| 1 | 芒果丁+爆爆珠特写，手部动作 | 8s | 11MB |
| 2 | 椰乳从椰子壳倒入，杯壁水珠 | 8s | 4.9MB |
| 3 | 沙冰倒入形成分层，冰晶闪烁 | 8s | 6.8MB |
| 4 | 完成品展示，薄荷叶装饰 | 8s | 11MB |

**性能统计**：

| 指标 | 数据 |
|------|------|
| 总耗时 | ~5 分钟 |
| 编剧 Agent | 20s / 1,482 tokens |
| 配音 Agent | 50s / 4 段音频 |
| 视频 Agent | ~4min / 4 段视频 (33MB) |
| 合并输出 | ~30s |
| **最终视频** | **32 秒 / 21MB** |

---

## 快速开始

### 1. 环境准备

```bash
# Python 3.10+
python3 -m venv venv
source venv/bin/activate
pip install openai requests

# ffmpeg（音视频处理）
sudo apt install ffmpeg  # Ubuntu/Debian
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env 填入：
# MIMO_API_KEY=你的MiMo Token Plan Key (tp-xxx)
# ARK_API_KEY=你的火山引擎方舟 Key (ark-xxx)
```

### 3. 配置 TTS

```bash
git clone https://github.com/XiaoMi/MiMo.git ~/MiMo-Skills
```

### 4. 运行

```bash
source .env

# 四模型管线（含视频）
python3 scripts/full_pipeline.py --topic "芒果椰椰冰 — 夏日必喝" --voice "冰糖"

# 三模型管线（仅音频，无需火山引擎Key）
python3 scripts/demo_pipeline.py --topic "芒果椰椰冰" --voice "冰糖"
```

### 5. 查看产出

```bash
ls /tmp/mimo-*/
# script.json        — 脚本结构化数据
# shot_1~4.wav       — 各镜头配音
# video_1~4.mp4      — 各镜头视频
# final_with_voice.mp4 — 完整版含配音
# final_compressed.mp4 — 压缩版
# review.json        — 审稿评分
# stats.json         — 性能统计
# run_log.txt        — 完整运行日志
```

---

## 技术亮点

### 1. 联网搜索驱动的脚本创作

编剧 Agent 在创作前先通过 MiMo 联网搜索获取真实产品信息（配方、制作过程、外观特征），确保视频提示词基于真实产品而非凭空想象。

### 2. 情绪驱动配音

编剧 Agent 为每个镜头标注情绪（"惊喜""治愈""兴奋""满足"），配音 Agent 将情绪注入 TTS，让同一音色在不同镜头呈现不同情感。

### 3. 真实配方驱动的视频生成

视频提示词基于真实产品配方（精确到克数），描述真实的颜色层次、制作动作、光线角度，而非抽象的艺术描述。

### 4. 质量评审闭环

审稿 Agent 从 5 个维度评分，如果总分低于阈值可以自动触发重写。

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
└── scripts/
    ├── full_pipeline.py         # 四模型管线（含视频，推荐）
    ├── demo_pipeline.py         # 三模型管线（仅音频）
    ├── multi_agent_pipeline.py  # 三模型管线（旧版）
    └── video_pipeline.py        # 四模型管线（旧版）
```

---

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| LLM | MiMo-V2.5-Pro / MiMo-V2.5 | 小米 Token Plan API |
| TTS | MiMo-V2.5-TTS | 8 种音色、情绪控制 |
| 视频 | Seedance 1.5 Pro | 火山引擎方舟 API |
| 音频 | ffmpeg | 音频合并与处理 |
| 调度 | Python pipeline | 状态管理、异常处理 |

---

## 已知限制

- Seedance 视频生成每段 60-75 秒，4 段约 4-5 分钟
- 视频质量受限于 AI 生成能力，与真实拍摄有差距
- TTS 配音时长与视频时长需要手动对齐
- 需要 MiMo Token Plan + 火山引擎方舟两个 API Key

---

## 扩展方向

- [ ] **图生视频模式** — 用真实产品照片作为首帧，提升视频真实感
- [ ] **批量生产模式** — 一次输入多个选题，批量生成
- [ ] **平台发布集成** — 自动适配抖音/快手/B站的格式和标题
- [ ] **数据反馈闭环** — 根据视频播放数据优化脚本策略

---

## License

MIT
