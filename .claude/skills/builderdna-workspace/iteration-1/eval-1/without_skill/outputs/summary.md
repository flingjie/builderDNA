# Karpathy & Geohot GitHub 分析总结

## 方法

1. 使用 GitHub REST API (`curl` + `jq`) 获取两人所有的公开仓库数据
2. 分别获取 karpathy 和 geohot 各 30 个仓库的完整信息（描述、语言、star数、推送时间）
3. 深入阅读核心项目的 README（autoresearch, nanochat, llm-council, factoring, nanocode）
4. 获取 tinygrad 组织和 commaai 组织的仓库列表
5. 对数据进行分析、分类、对比，提炼技术方向

## 结果

### Karpathy (@karpathy) 技术方向
- **AI Agent 自主研究**：autoresearch (91k stars) — AI自动进行ML训练实验
- **极低成本 LLM 训练**：nanochat (56k stars) — $100内训练ChatGPT级模型
- **多 LLM 协作系统**：llm-council (22k stars) — 多模型互审+最终评议
- **LLM 工具链**：rustbpe (tokenizer重写)、reader3 (LLM共读)、rendergit (repo渲染)
- **哲学**：Nano极简、Agent自动化、Vibe Coding

### Geohot (@geohot) 技术方向
- **GPU 底层编程**：tinygrad (33k stars)持续迭代、gpuocelot(PTX编译)、GPU固件
- **操作系统开发**：tinyos、vamOS(comma新OS)
- **极简工具**：nanocode (250行Claude Code替代)、minikeyvalue (1000行分布式KV)
- **自动驾驶**：openpilot (63k stars) 持续活跃开发
- **密码学探索**：factoring — 多项式时间因式分解算法
- **硬件黑客**：BTLE充电器控制、Tenstorrent芯片底层访问
- **哲学**：Tiny极简、硬件至上、反复杂化

### 潜在产品方向
1. AI Agent 自主实验平台 (SaaS)
2. 多 LLM 协作决策引擎 (企业级)
3. 极简本地 AI 编程助手 (硬件+软件)
4. 低成本 LLM 训练云服务
5. LLM + 硬件交互 IoT 平台
6. 车载 AI 助手/自动驾驶开发套件
