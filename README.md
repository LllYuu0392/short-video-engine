# 🎬 MiMo Content Pipeline

四模型协同短视频内容生产管线 —— 从一个选题到一条带配音的完整短视频，5分钟搞定。

## 架构

```
┌──────────────────────────────────────────────────────────┐
│                    Hermes Agent (调度层)                    │
│              规划 · 决策 · 监控 · 异常处理                     │
├──────────┬──────────┬──────────────┬──────────────────────┤
│ Step 1   │ Step 2   │   Step 3     │      Step 4          │
│ Pro 编剧 │ TTS 配音 │ Seedance 视频 │    V2.5 审稿         │
│ MiMo-V2.5│ MiMo-TTS │ Seedance-1.5 │    MiMo-V2.5        │
│ -Pro     │          │ -Pro         │                      │
├──────────┼──────────┼──────────────┼──────────────────────┤
│ 脚本 JSON │ .wav 音频 │  .mp4 视频   │   评分 + 建议         │
└──────────┴──────────┴──────────────┴──────────────────────┘
                           │
                    ┌──────┴──────┐
                    │ ffmpeg 合并  │
                    │ 音视频对齐   │
                    │ 压缩输出    │
                    └──────┬──────┘
                           ▼
                  final_with_audio.mp4
```

## 模型分工

| 模型 | 角色 | 能力 | API |
|------|------|------|-----|
| MiMo-V2.5-Pro | 编剧/策划 | 脚本创作、分镜拆解、视频提示词生成 | MiMo Token Plan |
| MiMo-V2.5-TTS | 配音演员 | 语音合成、8种音色、情绪控制、唱歌 | MiMo Token Plan |
| Seedance-1.5-Pro | 视觉导演 | 文生视频（竖屏9:16，含音频） | 火山引擎方舟 |
| MiMo-V2.5 | 审稿/评审 | 质量评分、内容审核、改进建议 | MiMo Token Plan |

## 为什么这么做

**痛点**：一个人做短视频，从选题→写脚本→录音频→找素材→剪视频，大半天就没了，产出还不稳定。

**方案**：把每个环节拆开，交给专门的模型去做，用 Agent 当调度中心。不是简单的 prompt chain——里面有状态管理、异常处理、自动重试。

**效果**：

| 指标 | 人工 | 管线 |
|------|------|------|
| 单条视频耗时 | 2-4小时 | ~5分钟 |
| 日产量 | 1-2条 | 3-5条 |
| 质量一致性 | 不稳定 | 审稿闭环保障 |

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
# 编辑 .env 填入你的 key
```

需要：
- `MIMO_API_KEY` — MiMo Token Plan API Key（格式 `tp-xxx`）
- `ARK_API_KEY` — 火山引擎方舟 API Key（格式 `ark-xxx`）

### 3. 安装 TTS 依赖

```bash
git clone https://github.com/XiaoMi/MiMo.git ~/MiMo-Skills
cd ~/MiMo-Skills
# 按照仓库说明安装 TTS 相关依赖
```

### 4. 运行

```bash
source .env

# 四模型管线（含视频）
python3 scripts/video_pipeline.py --topic "夏日杨枝甘露" --voice "冰糖"

# 三模型管线（仅音频）
python3 scripts/multi_agent_pipeline.py --topic "夏日杨枝甘露" --voice "冰糖"
```

## 工程细节

### JSON 容错解析

LLM 返回的 JSON 经常格式不统一（中英文字段混用、可能被截断）。用正则提取 + 容错映射：

```python
def parse_json_response(raw):
    """宽松 JSON 提取，容忍 LLM 输出格式不一致"""
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    m = re.search(r'\{.*\}', raw.strip(), re.DOTALL)
    if m:
        return json.loads(m.group())
    raise ValueError(f"无法从响应中提取 JSON: {raw[:200]}")
```

### 音视频时长对齐

TTS 配音通常比视频短很多（4段旁白~10秒 vs 4段视频~27秒）。用 ffmpeg `apad` 按镜头时长补齐静音：

```bash
ffmpeg -y -i shot_1.wav -af "apad=whole_dur=8" -t 8 padded_1.wav
```

### Seedance 异步任务

视频生成是异步的，每个镜头 60-75 秒。需要轮询 task 状态直到 `succeeded`。

### 视频压缩

合并后视频可能超过 30MB（飞书上传限制），用 CRF 28 压缩：

```bash
ffmpeg -y -i input.mp4 -vf "scale=-2:720" -c:v libx264 -crf 28 -preset fast \
  -c:a aac -b:a 64k -movflags +faststart output.mp4
```

实测 30MB → ~2MB，画质可接受。

## 使用场景

- 抖音/快手短视频批量生产
- 饮品/美食推广视频
- 有声内容创作
- 产品介绍视频

## 技术栈

- **LLM**: MiMo-V2.5-Pro / MiMo-V2.5（小米 Token Plan）
- **TTS**: MiMo-V2.5-TTS（8种音色，情绪控制）
- **视频**: Seedance-1.5-Pro（火山引擎方舟）
- **调度**: 自定义 Python pipeline + Agent 协同
- **音视频**: ffmpeg

## License

MIT
