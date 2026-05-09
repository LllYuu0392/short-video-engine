#!/usr/bin/env python3
"""
四模型协同：Pro 编剧 → TTS 配音 → Seedance 视频 → V2.5 审稿

用法：
    source .env
    python3 video_pipeline.py --topic "夏日杨枝甘露" --voice "冰糖"

环境变量：
    MIMO_API_KEY  - MiMo Token Plan API Key (tp-xxx)
    ARK_API_KEY   - 火山引擎方舟 API Key (ark-xxx)
"""

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

import requests
from openai import OpenAI

# ============ 配置 ============
MIMO_KEY = os.environ.get("MIMO_API_KEY")
MIMO_URL = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
ARK_KEY = os.environ.get("ARK_API_KEY")
ARK_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
SEEDANCE_MODEL = os.environ.get("SEEDANCE_MODEL", "doubao-seedance-1-5-pro-251215")
TTS_SCRIPTS = Path(os.environ.get("TTS_SCRIPTS", Path.home() / "MiMo-Skills/skills/mimo-v2-5-tts/scripts"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/tmp/mimo-video-pipeline"))


def log(stage, msg):
    print(f"\n{'=' * 55}\n  [{stage}] {msg}\n{'=' * 55}", flush=True)


def parse_json(raw):
    """宽松 JSON 提取，容忍 LLM 输出格式不一致（中英文字段混用、代码块包裹等）"""
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
    client = OpenAI(api_key=MIMO_KEY, base_url=MIMO_URL)
    prompt = f"""你是专业短视频编剧和视觉导演。为以下主题创作短视频脚本，分4个镜头。

主题：{topic}

每镜头含：
- scene: 画面描述
- narration: 旁白（≤15字）
- duration: 时长（5-8秒）
- emotion: 语气（如"温暖""欢快""沉稳"）
- video_prompt: 中文视频提示词，写实电影风格，描述运镜、光影、色调

严格按以下JSON输出，不要添加其他内容：
{{"title":"标题","style":"风格","shots":[{{"scene":"","narration":"","duration":6,"emotion":"","video_prompt":"电影感特写..."}}]}}"""

    resp = client.chat.completions.create(
        model="mimo-v2.5-pro",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=1500,
    )
    script = parse_json(resp.choices[0].message.content)
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
        else:
            print(f"  镜头{i} ✗ TTS 失败")
    log("TTS 配音", f"完成 {len(audio_files)}/{len(script['shots'])} 段")
    return audio_files


# ============ Agent: Seedance 视频 ============
def agent_video(script):
    log("Seedance 视频", f"生成 {len(script['shots'])} 段视频...")
    video_files = []
    for i, shot in enumerate(script["shots"], 1):
        prompt = shot.get("video_prompt", shot.get("scene", ""))
        duration = min(shot.get("duration", 5), 8)
        print(f"\n  镜头{i}: 提交任务...")
        try:
            resp = requests.post(
                f"{ARK_URL}/contents/generations/tasks",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {ARK_KEY}",
                },
                json={
                    "model": SEEDANCE_MODEL,
                    "content": [{"type": "text", "text": prompt}],
                    "generate_audio": True,
                    "ratio": "9:16",
                    "duration": duration,
                    "watermark": False,
                },
                timeout=30,
            )
            data = resp.json()
            if resp.status_code != 200 or "id" not in data:
                print(f"  镜头{i} ✗ 创建任务失败: {data}")
                continue
            task_id = data["id"]
            print(f"  镜头{i} 任务ID: {task_id}")
        except Exception as e:
            print(f"  镜头{i} ✗ {e}")
            continue

        # 轮询等待（最长5分钟）
        start = time.time()
        video_url = None
        while time.time() - start < 300:
            time.sleep(15)
            try:
                poll = requests.get(
                    f"{ARK_URL}/contents/generations/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {ARK_KEY}"},
                    timeout=15,
                ).json()
                status = poll.get("status", "unknown")
                print(f"  镜头{i} {status} ({int(time.time() - start)}s)", flush=True)
                if status == "succeeded":
                    video_url = poll.get("content", {}).get("video_url", "")
                    break
                if status in ("failed", "cancelled"):
                    break
            except Exception:
                pass

        if video_url:
            out = OUTPUT_DIR / f"video_{i}.mp4"
            try:
                out.write_bytes(requests.get(video_url, timeout=60).content)
                video_files.append(str(out))
                print(f"  镜头{i} ✓ {out.stat().st_size // 1024}KB")
            except Exception as e:
                print(f"  镜头{i} ✗ 下载失败: {e}")

    log("Seedance 视频", f"完成 {len(video_files)}/{len(script['shots'])} 段")
    return video_files


# ============ Agent: V2.5 审稿 ============
def agent_reviewer(script):
    log("V2.5 审稿", "正在审阅...")
    client = OpenAI(api_key=MIMO_KEY, base_url=MIMO_URL)
    prompt = f"""审阅以下短视频脚本，从5个维度评分（1-10）：
1. 吸引力 — 开头是否抓人
2. 口语感 — 旁白是否自然
3. 节奏感 — 镜头时长是否合理
4. 食欲感/感染力 — 画面描述是否有冲击力
5. 一致性 — 整体风格是否统一

脚本：{json.dumps(script, ensure_ascii=False)}

每项给分数和简短理由，最后一句话总结是否通过（7分以上为通过）。"""
    resp = client.chat.completions.create(
        model="mimo-v2.5",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=500,
    )
    text = resp.choices[0].message.content.strip()
    log("V2.5 审稿", "完成")
    print(text[:500])
    return {"review_text": text}


# ============ 合并 ============
def merge_video(video_files, audio_files, script):
    if not video_files:
        return ""

    # 拼接视频片段
    vlist = OUTPUT_DIR / "video_list.txt"
    vlist.write_text("\n".join(f"file '{v}'" for v in video_files))
    merged_v = OUTPUT_DIR / "merged.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(vlist), "-c", "copy", str(merged_v)],
        capture_output=True, timeout=60,
    )

    if audio_files and script:
        # 每段配音按时长补齐静音（解决 TTS 音频比视频短的问题）
        padded = []
        for i, (af, shot) in enumerate(zip(audio_files, script.get("shots", [])), 1):
            dur = shot.get("duration", 5)
            p = OUTPUT_DIR / f"padded_{i}.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-i", af, "-af", f"apad=whole_dur={dur}", "-t", str(dur), str(p)],
                capture_output=True, timeout=30,
            )
            padded.append(str(p))

        alist = OUTPUT_DIR / "audio_list.txt"
        alist.write_text("\n".join(f"file '{a}'" for a in padded))
        merged_a = OUTPUT_DIR / "merged_audio_full.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(alist), "-c", "copy", str(merged_a)],
            capture_output=True, timeout=30,
        )

        # 合并音视频（用 -map 显式指定源，避免轨道丢失）
        final = OUTPUT_DIR / "final_with_audio.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(merged_v), "-i", str(merged_a),
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                str(final),
            ],
            capture_output=True, timeout=60,
        )
        if final.exists():
            log("合并", f"完成！{final.stat().st_size // 1024}KB → {final}")
            return str(final)

    if merged_v.exists():
        return str(merged_v)
    return ""


# ============ 主流程 ============
def main():
    parser = argparse.ArgumentParser(description="四模型协同短视频管线")
    parser.add_argument("--topic", required=True, help="视频主题")
    parser.add_argument("--voice", default="冰糖", help="TTS 音色名称")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()

    script = agent_producer(args.topic)
    audio_files = agent_tts(script, args.voice)
    video_files = agent_video(script)
    review = agent_reviewer(script)
    final = merge_video(video_files, audio_files, script)

    elapsed = time.time() - start
    log("完成", f"总耗时 {elapsed:.0f} 秒")
    if final:
        print(f"  输出: {final}")

    # 保存元数据
    (OUTPUT_DIR / "meta.json").write_text(
        json.dumps(
            {"script": script, "review": review, "final": final,
             "video_files": video_files, "audio_files": audio_files},
            ensure_ascii=False, indent=2,
        )
    )


if __name__ == "__main__":
    main()
