# 架构详解

## 系统概述
MiMo Content Factory 是一个基于多Agent协同的内容生产系统。

## Agent 设计
- 编剧Agent: 负责脚本创作和分镜拆解
- 配音Agent: 负责语音合成和情绪控制
- 审稿Agent: 负责质量评分和改进建议

## 数据流
用户输入topic -> 编剧Agent生成script.json -> 配音Agent生成shot_N.wav -> 审稿Agent生成review.json -> ffmpeg合并
