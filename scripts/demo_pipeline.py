#!/usr/bin/env python3
"""
MiMo Content Factory — 三模型协同演示管线
MiMo-V2.5-Pro (编剧) → MiMo-V2.5-TTS (配音) → MiMo-V2.5 (审稿)

用法：
    MIMO_API_KEY=xxx python3 demo_pipeline.py --topic "夏日芒果冰饮" --voice "冰糖"

产出：
    output_dir/script.json    — 脚本结构化数据
    output_dir/shot_N.wav     — 各镜头配音
    output_dir/review.json    — 审稿结果
    output_dir/run_log.txt    — 运行日志
    output_dir/stats.json     — 性能统计
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from openai import OpenAI

# ============ 配置 ============
API_KEY = os.environ.get("MIMO_API_KEY")
BASE_URL = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
TTS_SCRIPTS = Path(os.environ.get("TTS_SCRIPTS", Path.home() / "MiMo-Skills/skills/mimo-v2-5-tts/scripts"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/tmp/mimo-demo"))

# 运行日志
RUN_LOG = []


def log(stage, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] [{stage}] {msg}"
    print(f"\n{'=' * 55}\n  {line}\n{'=' * 55}", flush=True)
    RUN_LOG.append(line)


def log_detail(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}]   {msg}"
    print(f"  {line}", flush=True)
    RUN_LOG.append(line)


def get_client():
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


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


# ============ Agent 1: Pro 编剧 ============
def agent_scriptwriter(topic, extra_context=""):
    log("编剧 Agent", f"正在为「{topic}」创作脚本...")
    t0 = time.time()

    client = get_client()
    context_section = f"\n\n额外背景信息：\n{extra_context}" if extra_context else ""

    prompt = f"""你是专业短视频编剧，擅长为饮品/美食店创作抖音短视频脚本。

主题：{topic}{context_section}

要求：
1. 分4个镜头，总时长约30秒
2. 风格：温暖治愈、有食欲感、适合抖音竖屏
3. 旁白口语化，像在跟朋友聊天

每镜头必须包含：
- scene: 画面描述（具体到颜色、光线、构图）
- narration: 旁白文案（≤15字，口语化）
- duration: 时长秒数（5-8秒）
- emotion: 情绪语气（如"温暖""欢快""沉稳""惊喜"）
- video_prompt: AI视频生成提示词（中文，描述运镜、光影、色调、质感）

严格按以下JSON输出，不要添加任何其他内容：
{{"title":"视频标题","style":"整体风格","target_platform":"抖音","shots":[{{"scene":"","narration":"","duration":6,"emotion":"","video_prompt":""}}]}}"""

    resp = client.chat.completions.create(
        model="mimo-v2.5-pro",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=1500,
    )

    raw_response = resp.choices[0].message.content
    script = parse_json_response(raw_response)

    t1 = time.time()
    tokens = resp.usage.total_tokens if resp.usage else 0

    log("编剧 Agent", f"完成！{len(script['shots'])} 个镜头")
    log_detail(f"标题: {script.get('title', 'N/A')}")
    log_detail(f"风格: {script.get('style', 'N/A')}")
    for i, shot in enumerate(script['shots'], 1):
        log_detail(f"  镜头{i}: {shot['narration']} ({shot['duration']}s, {shot['emotion']})")

    return script, {"agent": "scriptwriter", "time": t1 - t0, "tokens": tokens}


# ============ Agent 2: TTS 配音 ============
def agent_voice_actor(script, voice):
    log("配音 Agent", f"使用「{voice}」生成 {len(script['shots'])} 段配音...")
    t0 = time.time()
    total_bytes = 0

    audio_files = []
    for i, shot in enumerate(script["shots"], 1):
        emotion = shot.get("emotion", "")
        text = f"({emotion}){shot['narration']}" if emotion else shot["narration"]
        out = OUTPUT_DIR / f"shot_{i}.wav"

        cmd = [
            str(TTS_SCRIPTS / "mimo_tts.py"),
            "--text", text,
            "--voice", voice,
            "--output", str(out),
        ]
        if emotion:
            cmd[1:1] = ["--context", f"用{emotion}的语气"]

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and out.exists():
            size = out.stat().st_size
            total_bytes += size
            audio_files.append(str(out))
            log_detail(f"  镜头{i} ✓ {size // 1024}KB — \"{shot['narration'][:20]}\"")
        else:
            log_detail(f"  镜头{i} ✗ 失败: {r.stderr[:100]}")

    t1 = time.time()
    log("配音 Agent", f"完成 {len(audio_files)}/{len(script['shots'])} 段, 共 {total_bytes // 1024}KB")

    return audio_files, {"agent": "voice_actor", "time": t1 - t0, "audio_count": len(audio_files), "total_kb": total_bytes // 1024}


# ============ Agent 3: V2.5 审稿 ============
def agent_reviewer(script, audio_files):
    log("审稿 Agent", "正在审阅脚本质量和配音效果...")
    t0 = time.time()

    client = get_client()

    script_summary = json.dumps(script, ensure_ascii=False)
    audio_summary = "\n".join([f"  镜头{i}: {Path(f).name} ({Path(f).stat().st_size // 1024}KB)" for i, f in enumerate(audio_files, 1)])

    prompt = f"""你是短视频内容质量评审专家。审阅以下AI生成的短视频项目：

## 脚本
{script_summary}

## 配音文件
{audio_summary}

请从以下5个维度评分（1-10分），每项给出分数和1句话理由：

1. **吸引力** — 标题和开头是否能吸引用户停留
2. **口语感** — 旁白是否自然、像朋友聊天
3. **节奏感** — 镜头时长分配是否合理
4. **食欲感** — 画面描述是否让人想下单
5. **一致性** — 整体风格是否统一协调

最后给出总分（5项平均）和一句话改进建议。

严格按JSON格式输出：
{{"scores":{{"吸引力":0,"口语感":0,"节奏感":0,"食欲感":0,"一致性":0}},"total":0,"suggestion":"改进建议"}}"""

    resp = client.chat.completions.create(
        model="mimo-v2.5",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=800,
    )

    raw = resp.choices[0].message.content
    t1 = time.time()
    tokens = resp.usage.total_tokens if resp.usage else 0

    try:
        review = parse_json_response(raw)
    except Exception:
        review = {"review_text": raw}

    log("审稿 Agent", "完成")
    if "scores" in review:
        for k, v in review["scores"].items():
            log_detail(f"  {k}: {v}/10")
        log_detail(f"  总分: {review.get('total', 'N/A')}/10")
        log_detail(f"  建议: {review.get('suggestion', 'N/A')}")
    else:
        log_detail(f"  {raw[:300]}")

    return review, {"agent": "reviewer", "time": t1 - t0, "tokens": tokens}


# ============ 合并音频 ============
def merge_audio(audio_files):
    log("合并", f"将 {len(audio_files)} 段音频合并为完整配音...")
    t0 = time.time()

    # 生成 ffmpeg concat 列表
    concat_list = OUTPUT_DIR / "concat.txt"
    with open(concat_list, "w") as f:
        for af in audio_files:
            f.write(f"file '{af}'\n")

    output = OUTPUT_DIR / "full_voiceover.wav"
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(output)],
        capture_output=True, text=True, timeout=30,
    )

    t1 = time.time()
    if r.returncode == 0 and output.exists():
        size = output.stat().st_size
        log("合并", f"完成！{size // 1024}KB → {output}")
        return str(output), {"agent": "merge", "time": t1 - t0, "size_kb": size // 1024}
    else:
        log("合并", f"失败: {r.stderr[:200]}")
        return None, {"agent": "merge", "time": t1 - t0, "error": r.stderr[:200]}


# ============ 主流程 ============
def main():
    parser = argparse.ArgumentParser(description="MiMo Content Factory 演示管线")
    parser.add_argument("--topic", required=True, help="视频主题")
    parser.add_argument("--voice", default="冰糖", help="TTS 音色（冰糖/可乐/泡泡等）")
    parser.add_argument("--extra-context", default="", help="额外背景信息")
    args = parser.parse_args()

    if not API_KEY:
        print("错误: 请设置 MIMO_API_KEY 环境变量", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log("MiMo Content Factory", f"主题: {args.topic} | 音色: {args.voice}")
    log("MiMo Content Factory", f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    total_start = time.time()

    # Agent 1: 编剧
    script, stats_sw = agent_scriptwriter(args.topic, args.extra_context)

    # Agent 2: 配音
    audio_files, stats_va = agent_voice_actor(script, args.voice)

    # Agent 3: 审稿
    review, stats_rv = agent_reviewer(script, audio_files)

    # 合并音频
    full_audio, stats_mg = merge_audio(audio_files)

    total_time = time.time() - total_start

    # 保存所有产出
    (OUTPUT_DIR / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2)
    )
    (OUTPUT_DIR / "review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2)
    )
    (OUTPUT_DIR / "run_log.txt").write_text("\n".join(RUN_LOG))

    all_stats = {
        "topic": args.topic,
        "voice": args.voice,
        "timestamp": datetime.now().isoformat(),
        "total_time": round(total_time, 1),
        "agents": [stats_sw, stats_va, stats_rv, stats_mg],
        "shot_count": len(script.get("shots", [])),
        "audio_count": len(audio_files),
    }
    (OUTPUT_DIR / "stats.json").write_text(
        json.dumps(all_stats, ensure_ascii=False, indent=2)
    )

    log("完成", f"总耗时 {total_time:.1f} 秒")
    log("完成", f"产出目录: {OUTPUT_DIR}")
    log("完成", f"文件: script.json, review.json, run_log.txt, stats.json")
    if full_audio:
        log("完成", f"完整配音: {full_audio}")

    print(f"\n{'=' * 55}")
    print(f"  全部完成！产出在 {OUTPUT_DIR}")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
