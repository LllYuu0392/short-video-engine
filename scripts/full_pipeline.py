#!/usr/bin/env python3
"""
MiMo Content Factory — 四模型协同完整管线
Pro 编剧 → TTS 配音 → Seedance 视频 → V2.5 审稿 → ffmpeg 合并

用法：
    python3 full_pipeline.py --topic "芒果椰椰冰" --voice "冰糖"
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

import requests
from openai import OpenAI

# ============ 配置 ============
MIMO_KEY = os.environ.get("MIMO_API_KEY")
MIMO_URL = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
ARK_KEY = os.environ.get("ARK_API_KEY", "ark-595b4b58-f6fa-4749-823c-08cb8891a6d0-50071")
ARK_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
SEEDANCE_MODEL = "doubao-seedance-1-5-pro-251215"
TTS_SCRIPTS = Path(os.environ.get("TTS_SCRIPTS", Path.home() / "MiMo-Skills/skills/mimo-v2-5-tts/scripts"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/tmp/mimo-full-pipeline"))

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


def parse_json_response(raw):
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    m = re.search(r'\{.*\}', raw.strip(), re.DOTALL)
    if m:
        return json.loads(m.group())
    raise ValueError(f"无法从响应中提取 JSON: {raw[:200]}")


# ============ Agent 1: Pro 编剧 ============
def agent_scriptwriter(topic):
    log("Step 1: Pro 编剧", f"MiMo-V2.5-Pro | 为「{topic}」创作脚本...")
    t0 = time.time()
    client = OpenAI(api_key=MIMO_KEY, base_url=MIMO_URL)

    prompt = f"""你是专业短视频编剧。为以下主题创作30秒短视频脚本，分4个镜头。

主题：{topic}

每镜头含：scene(画面)、narration(旁白≤15字)、duration(秒)、emotion(语气)、video_prompt(中文，描述运镜光影，Seedance视频生成用)。

严格JSON输出：
{{"title":"标题","style":"风格","shots":[{{"scene":"","narration":"","duration":6,"emotion":"","video_prompt":"电影感特写..."}}]}}"""

    resp = client.chat.completions.create(
        model="mimo-v2.5-pro",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8, max_tokens=1500,
    )
    script = parse_json_response(resp.choices[0].message.content)
    t1 = time.time()
    tokens = resp.usage.total_tokens if resp.usage else 0

    log("Step 1: Pro 编剧", f"完成! {len(script['shots'])} 个镜头 | {t1-t0:.1f}s | {tokens} tokens")
    for i, s in enumerate(script['shots'], 1):
        log_detail(f"镜头{i}: {s['narration']} ({s['duration']}s, {s['emotion']})")
    return script, {"step": "scriptwriter", "time": round(t1-t0, 1), "tokens": tokens}


# ============ Agent 2: TTS 配音 ============
def agent_tts(script, voice):
    log("Step 2: TTS 配音", f"MiMo-V2.5-TTS | 使用「{voice}」生成 {len(script['shots'])} 段配音...")
    t0 = time.time()
    audio_files = []

    for i, shot in enumerate(script["shots"], 1):
        emotion = shot.get("emotion", "")
        text = f"({emotion}){shot['narration']}" if emotion else shot["narration"]
        out = OUTPUT_DIR / f"shot_{i}.wav"
        cmd = [str(TTS_SCRIPTS / "mimo_tts.py"), "--text", text, "--voice", voice, "--output", str(out)]
        if emotion:
            cmd[1:1] = ["--context", f"用{emotion}的语气"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and out.exists():
            audio_files.append(str(out))
            log_detail(f"  镜头{i} OK {out.stat().st_size//1024}KB")
        else:
            log_detail(f"  镜头{i} FAIL: {r.stderr[:100]}")

    t1 = time.time()
    log("Step 2: TTS 配音", f"完成 {len(audio_files)}/{len(script['shots'])} 段 | {t1-t0:.1f}s")
    return audio_files, {"step": "tts", "time": round(t1-t0, 1), "count": len(audio_files)}


# ============ Agent 3: Seedance 视频 ============
def agent_seedance(script):
    log("Step 3: Seedance 视频", f"Doubao-Seedance-1.5-Pro | 生成 {len(script['shots'])} 段视频...")
    t0 = time.time()
    video_files = []
    headers = {"Authorization": f"Bearer {ARK_KEY}", "Content-Type": "application/json"}

    for i, shot in enumerate(script["shots"], 1):
        prompt = shot.get("video_prompt", shot.get("scene", ""))
        log_detail(f"  镜头{i} 提交任务: {prompt[:40]}...")

        # 创建任务
        try:
            resp = requests.post(
                f"{ARK_URL}/contents/generations/tasks",
                headers=headers,
                json={
                    "model": SEEDANCE_MODEL,
                    "content": [{"type": "text", "text": prompt}],
                    "generate_audio": True,
                    "ratio": "9:16",
                    "duration": 5,
                    "watermark": False,
                },
                timeout=30,
            )
            data = resp.json()
            task_id = data.get("id")
            if not task_id:
                log_detail(f"  镜头{i} 任务创建失败: {data}")
                continue
            log_detail(f"  镜头{i} 任务ID: {task_id}")
        except Exception as e:
            log_detail(f"  镜头{i} 请求失败: {e}")
            continue

        # 轮询等待
        for attempt in range(20):  # 最多等 5 分钟
            time.sleep(15)
            try:
                status_resp = requests.get(
                    f"{ARK_URL}/contents/generations/tasks/{task_id}",
                    headers=headers, timeout=15,
                )
                status_data = status_resp.json()
                status = status_data.get("status", "unknown")
                log_detail(f"  镜头{i} 状态: {status} ({attempt*15}s)")

                if status == "succeeded":
                    video_url = status_data.get("content", {}).get("video_url")
                    if video_url:
                        out = OUTPUT_DIR / f"video_{i}.mp4"
                        video_data = requests.get(video_url, timeout=60).content
                        out.write_bytes(video_data)
                        video_files.append(str(out))
                        log_detail(f"  镜头{i} OK {out.stat().st_size//1024//1024}MB")
                    break
                elif status in ("failed", "cancelled"):
                    log_detail(f"  镜头{i} 失败: {status_data}")
                    break
            except Exception as e:
                log_detail(f"  镜头{i} 轮询异常: {e}")

    t1 = time.time()
    log("Step 3: Seedance 视频", f"完成 {len(video_files)}/{len(script['shots'])} 段 | {t1-t0:.1f}s")
    return video_files, {"step": "seedance", "time": round(t1-t0, 1), "count": len(video_files)}


# ============ Agent 4: V2.5 审稿 ============
def agent_reviewer(script, audio_files, video_files):
    log("Step 4: V2.5 审稿", "MiMo-V2.5 | 审阅脚本质量和产出效果...")
    t0 = time.time()
    client = OpenAI(api_key=MIMO_KEY, base_url=MIMO_URL)

    prompt = f"""审阅短视频脚本，5维度评分(1-10)：吸引力/口语感/节奏感/食欲感/一致性。
脚本：{json.dumps(script, ensure_ascii=False)}
音频：{len(audio_files)}段 | 视频：{len(video_files)}段
每项给分数和简短理由，最后一句话总结。

严格JSON输出：
{{"scores":{{"吸引力":0,"口语感":0,"节奏感":0,"食欲感":0,"一致性":0}},"total":0,"suggestion":"改进建议"}}"""

    resp = client.chat.completions.create(
        model="mimo-v2.5",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3, max_tokens=600,
    )
    review = parse_json_response(resp.choices[0].message.content)
    t1 = time.time()

    log("Step 4: V2.5 审稿", f"完成 | {t1-t0:.1f}s")
    if "scores" in review:
        for k, v in review["scores"].items():
            log_detail(f"  {k}: {v}/10")
        log_detail(f"  总分: {review.get('total', 'N/A')}/10")
        log_detail(f"  建议: {review.get('suggestion', 'N/A')}")
    return review, {"step": "reviewer", "time": round(t1-t0, 1)}


# ============ Step 5: 合并 ============
def merge_all(audio_files, video_files):
    log("Step 5: ffmpeg 合并", "拼接视频 + 配音 + 压缩...")
    t0 = time.time()

    # 合并视频
    video_concat = OUTPUT_DIR / "video_concat.txt"
    with open(video_concat, "w") as f:
        for vf in video_files:
            f.write(f"file '{vf}'\n")
    merged_video = OUTPUT_DIR / "merged_video.mp4"
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(video_concat), "-c", "copy", str(merged_video)],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        log_detail(f"  视频合并失败: {r.stderr[:200]}")
        return None, {"step": "merge", "time": 0, "error": "video merge failed"}

    # 合并音频
    audio_concat = OUTPUT_DIR / "audio_concat.txt"
    with open(audio_concat, "w") as f:
        for af in audio_files:
            f.write(f"file '{af}'\n")
    merged_audio = OUTPUT_DIR / "merged_audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_concat), "-c", "copy", str(merged_audio)],
        capture_output=True, text=True, timeout=30,
    )

    # 音视频合并（用视频自带音频 + TTS 配音混音）
    final_output = OUTPUT_DIR / "final_with_voice.mp4"
    r = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(merged_video),
        "-i", str(merged_audio),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(final_output),
    ], capture_output=True, text=True, timeout=60)

    t1 = time.time()
    if r.returncode == 0 and final_output.exists():
        size_mb = final_output.stat().st_size / 1024 / 1024
        log("Step 5: ffmpeg 合并", f"完成! {size_mb:.1f}MB | {final_output}")

        # 压缩版本
        compressed = OUTPUT_DIR / "final_compressed.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(final_output),
            "-vf", "scale=-2:720", "-c:v", "libx264", "-crf", "28", "-preset", "fast",
            "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart",
            str(compressed),
        ], capture_output=True, text=True, timeout=60)
        if compressed.exists():
            log_detail(f"  压缩版: {compressed.stat().st_size//1024//1024}MB")

        return str(final_output), {"step": "merge", "time": round(t1-t0, 1), "size_mb": round(size_mb, 1)}
    else:
        log_detail(f"  合并失败: {r.stderr[:200]}")
        return None, {"step": "merge", "time": round(t1-t0, 1), "error": r.stderr[:200]}


# ============ 主流程 ============
def main():
    parser = argparse.ArgumentParser(description="MiMo Content Factory 四模型完整管线")
    parser.add_argument("--topic", required=True, help="视频主题")
    parser.add_argument("--voice", default="冰糖", help="TTS 音色")
    args = parser.parse_args()

    if not MIMO_KEY:
        print("错误: 请设置 MIMO_API_KEY", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log("MiMo Content Factory (4-Model)", f"主题: {args.topic} | 音色: {args.voice}")
    log("MiMo Content Factory", f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    total_start = time.time()

    # Step 1: 编剧
    script, s1 = agent_scriptwriter(args.topic)

    # Step 2: 配音
    audio_files, s2 = agent_tts(script, args.voice)

    # Step 3: 视频
    video_files, s3 = agent_seedance(script)

    # Step 4: 审稿
    review, s4 = agent_reviewer(script, audio_files, video_files)

    # Step 5: 合并
    final_path, s5 = merge_all(audio_files, video_files)

    total_time = time.time() - total_start

    # 保存产出
    (OUTPUT_DIR / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2))
    (OUTPUT_DIR / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2))
    (OUTPUT_DIR / "run_log.txt").write_text("\n".join(RUN_LOG))
    (OUTPUT_DIR / "stats.json").write_text(json.dumps({
        "topic": args.topic, "voice": args.voice,
        "timestamp": datetime.now().isoformat(),
        "total_time": round(total_time, 1),
        "steps": [s1, s2, s3, s4, s5],
        "shot_count": len(script.get("shots", [])),
        "audio_count": len(audio_files),
        "video_count": len(video_files),
    }, ensure_ascii=False, indent=2))

    log("完成", f"总耗时 {total_time:.0f} 秒 ({total_time/60:.1f} 分钟)")
    log("完成", f"产出目录: {OUTPUT_DIR}")
    if final_path:
        log("完成", f"完整视频: {final_path}")

    print(f"\n{'=' * 55}")
    print(f"  全部完成！耗时 {total_time:.0f} 秒")
    print(f"  产出: {OUTPUT_DIR}")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
