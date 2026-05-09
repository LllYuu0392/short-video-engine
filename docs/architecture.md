# MiMo Content Pipeline

四模型协同短视频内容生产管线。给一个选题，自动产出带配音的完整短视频。

## 架构

- **MiMo-V2.5-Pro** → 编剧（脚本、分镜、视频提示词）
- **MiMo-V2.5-TTS** → 配音（8种音色、情绪控制）
- **Seedance-1.5-Pro** → 视频生成（竖屏9:16）
- **MiMo-V2.5** → 审稿（5维度评分、改进建议）
- **ffmpeg** → 音视频合并、压缩

## 核心问题与解法

详见 [architecture.md](architecture.md)

## 运行管线

```bash
# 四模型（含视频）
python3 scripts/video_pipeline.py --topic "主题" --voice "冰糖"

# 三模型（仅音频）
python3 scripts/multi_agent_pipeline.py --topic "主题" --voice "冰糖"
```
