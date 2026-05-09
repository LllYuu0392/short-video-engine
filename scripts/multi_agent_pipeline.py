#!/usr/bin/env python3
"""
三模型协同：MiMo-V2.5-Pro (编剧) → MiMo-V2.5-TTS (配音) → MiMo-V2.5 (审稿)

用法：
    source .env
    python3 multi_agent_pipeline.py --topic "夏日杨枝甘露" --voice "冰糖"

不需要 Seedance/火山引擎，仅用 MiMo 系列模型。
"""

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

from openai import OpenAI

# ============ 配置 ============
API_KEY = os.environ.get("MIMO_API_KEY")
BASE_URL = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
TTS_SCRIPTS = Path(os.environ.get("TTS_SCRIPTS", Path.home() / "MiMo-Skills/skills/mimo-v2-5-tts/scripts"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/tmp/mimo-multi-agent"))


def get_client():
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


def log(stage, msg):
    print(f"\n{'=' * 50}\n  [{stage}] {msg}\n{'=' * 50}", flush=True)


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


# ============ Agent: Pro 编剧 ============
def agent_producer(topic):
    log("Pro 编剧", f"正在为「{topic}」创作脚本...")
    client = get_client()
    prompt = f"""你是专业短视频编剧。为以下主题创作30秒短视频脚本，分4个镜头。

主题：{topic}

每镜头含：scene(画面)、narration(旁白≤15字)、duration(秒)、emotion(语气)、video_prompt(中文，描述运镜光影)。

严格JSON输出：
{{"title":"标题","style":"风格","shots":[{{"scene":"","narration":"","duration":6,"emotion":"","video_prompt":"电影感特写...}}]}}"""

    resp = client.chat.completions.create(
        model="mimo-v2.5-pro",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=1000,
    )
    script = parse_json_response(resp.choices[0].message.content)
    log("Pro 编剧", f"完成！{len(script['shots'])} 个镜头")
    return script


# ============ Agent: TTS 配音 ============
def agent_tts(script, voice):
    log("TTS 配音", f"使用「{voice}」生成 {len(script['shots'])} 段配音...")
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
            audio_files.append(str(out))
            print(f"  镜头{i} ✓ {out.stat().st_size // 1024}KB")
    log("TTS 配音", f"完成 {len(audio_files)}/{len(script['shots'])} 段")
    return audio_files


# ============ Agent: V2.5 审稿 ============
def agent_reviewer(script):
    log("V2.5 审稿", "正在审阅...")
    client = get_client()
    prompt = f"""审阅短视频脚本，5维度评分(1-10)：吸引力/口语感/节奏感/食欲感/一致性。
脚本：{json.dumps(script, ensure_ascii=False)}
每项给分数和简短理由，最后一句话总结。"""
    resp = client.chat.completions.create(
        model="mimo-v2.5",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=500,
    )
    review_text = resp.choices[0].message.content.strip()
    log("V2.5 审稿", "完成")
    print(review_text[:500])
    return {"review_text": review_text}


# ============ 主流程 ============
def main():
    parser = argparse.ArgumentParser(description="三模型协同管线（音频版）")
    parser.add_argument("--topic", required=True, help="视频主题")
    parser.add_argument("--voice", default="冰糖", help="TTS 音色名称")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()

    script = agent_producer(args.topic)
    audio_files = agent_tts(script, args.voice)
    review = agent_reviewer(script)

    elapsed = time.time() - start
    log("完成", f"总耗时 {elapsed:.1f} 秒，{len(audio_files)} 段音频")

    # 保存脚本
    (OUTPUT_DIR / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
