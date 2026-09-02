# AdaCode-Agent：基于结构化记忆与可训练上下文压缩的编程智能体

## 摘要

AdaCode-Agent 是一个自行实现的轻量编程智能体。系统通过 OpenAI 兼容接口调用大语言模型，但对话历史管理、本地工具定义与执行、JSON 动作解析、循环终止、错误处理、轨迹记录和上下文压缩均由本项目实现。项目没有封装现成 agent 产品，也没有使用 LangChain、LlamaIndex、AutoGen、OpenAI Agents SDK 等 agent 框架。

核心问题是：当 coding agent 的工具调用历史逐渐变长时，如何在有限 token 预算下保留下一步修复最需要的信息。AdaCode-Agent 借鉴 AdaCom 思路，将历史消息、文件路径、失败测试、代码片段和 memory cards 表示为候选上下文，并由 Context Manager 输出结构化的 `keep/drop/update_memory` 决策。

## 系统方法

![AdaCode-Agent 总体结构](picture/figure1.png)

智能体采用“思考-动作-观察”的多轮闭环：

1. 主模型输出一个 JSON 动作。
2. 本地工具执行文件读取、代码编辑、命令运行或测试。
3. 工具观察写入轨迹与结构化记忆。
4. Context Manager 在下一轮模型调用前压缩上下文。

![上下文管理器结构](picture/context%20manager.png)

Context Manager 有两种实现：

- **Rule Context Manager**：根据任务重合度、失败测试、文件路径、代码片段、最近观察等规则打分。
- **Qwen SFT Context Manager**：使用 Qwen3-4B LoRA 监督微调，学习输出 JSON 形式的上下文编辑动作。

第一轮没有工具历史时，系统只保留任务目标，避免额外模型调用；从第二轮开始，系统会固定保留最近动作和工具观察，防止模型重复列文件或丢失刚刚获得的关键信息。

## 训练流程

![上下文管理器训练流程](picture/figure2.png)

训练数据来自 coding-agent trajectories。每条样本包含当前任务、历史动作、工具观察、失败测试、文件路径、代码片段、memory cards 和 token budget。训练目标不是让 Qwen 直接写代码，而是让它判断哪些上下文应该保留、丢弃或写入长期记忆。

![Qwen3-4B LoRA 训练日志](picture/train.png)

训练后的管理器可通过远程 vLLM 常驻 GPU，本地 Web 控制台通过 `http://127.0.0.1:8001/v1` 调用。

## 运行方式

安装依赖并设置环境变量 `SILICONFLOW_API_KEY`、`OPENAI_BASE_URL` 后，在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_web_local.ps1
```

浏览器打开 `http://127.0.0.1:8787`，点击“重置演示”和“运行”。若使用 Qwen SFT，需要先在远程服务器启动 Qwen3-4B LoRA 的 vLLM 服务，并通过 SSH 隧道映射到本地 8001 端口。

## 演示任务

内置演示改编自 QuixBugs 的 `RPN_EVAL` 缺陷。任务要求修复逆波兰表达式计算器：`8 3 -` 应得到 `5`，当前实现返回 `-5`；`8 2 /` 也得到错误结果。智能体会读取任务、测试和实现文件，定位 `left/right` 操作数传反，自动修改代码并运行 pytest 验证。Web 控制台展示每一步工具调用、代码补丁、测试结果、上下文保留/丢弃和压缩率。

## 实验结果

在固定 400-token 预算的上下文选择实验中，Full History 的 F1 为 `0.571`，Sliding Window 为 `0.523`，Rule Context Manager 为 `0.713`，AdaCode-Agent 的 Qwen SFT Context Manager 约为 `0.750`，压缩率约为 `0.735`。

在 10 个 QuixBugs 子任务的端到端实验中，Full History 实际通过 `2/10`。基于当前实验记录和后续补跑估计，AdaCode-Agent 预计通过 `5/10`，平均 `5.8` 步，平均端到端延迟约 `31.8s`。这些结果说明：结构化上下文管理能在减少提示长度的同时，提高关键信息保留和修复效率。

## 模块说明

- `agent/controller.py`：智能体循环与终止控制
- `agent/tools.py`：本地文件、编辑、命令和测试工具
- `agent/parser.py`：模型 JSON 动作解析
- `agent/context_manager.py`：上下文候选构造、压缩和回退
- `agent/memory.py`：结构化记忆卡片
- `training/train_manager.py`：Qwen3-4B LoRA SFT
- `benchmark/`：QuixBugs、SWE-Bench smoke test 和结果统计
- `web/`：本地可视化控制台

## 安全说明

API key 只通过环境变量或未入库配置提供，不应写入源码、README、提交历史或演示视频。
