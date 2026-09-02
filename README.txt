Git仓库地址：
https://github.com/Acking646/adacode-agent

项目简介：
AdaCode-Agent 是一个自行实现的本地编程智能体。它通过 OpenAI 兼容接口调用大语言模型，但文件读写、命令执行、JSON 动作解析、多轮循环、错误处理、轨迹记录和上下文压缩都由本地代码完成；没有封装现成 agent 产品，也没有使用 agent 框架。

如何运行：
1. 安装依赖：pip install -r requirements.txt
2. 设置环境变量：SILICONFLOW_API_KEY，OPENAI_BASE_URL=https://api.siliconflow.cn/v1
3. 命令行运行：
python -m agent.main "修复项目使测试通过" --workspace examples/quixbugs_rpn_demo_project --model deepseek-ai/DeepSeek-V4-Flash
4. 可视化运行：
powershell -ExecutionPolicy Bypass -File scripts/start_web_local.ps1
浏览器打开 http://127.0.0.1:8787，点“重置演示”和“运行”。

特色功能：
智能体按“思考-动作-观察”循环工作，支持 list_files、read_file、edit_file、write_file、run_tests 等本地工具。核心设计是 AdaCom 启发的上下文管理器：每轮模型调用前，将任务、工具观察、失败测试、代码片段和结构化记忆转为候选上下文，再选择 keep/drop，压缩无关历史。系统内置规则管理器，也支持远程 vLLM 部署的 Qwen3-4B LoRA SFT 管理器；第一轮无工具历史时只保留任务，后续保留最近动作和工具观察，避免重复列文件。

演示任务：
内置案例改编自 QuixBugs 的 RPN_EVAL 缺陷。智能体会读取测试和实现，发现逆波兰表达式计算器把 left/right 操作数传反，自动修改代码并运行 pytest 验证。Web 控制台展示补丁、测试输出、上下文保留/丢弃和压缩率。

说明：
API key 只通过环境变量提供，不应写入仓库、README 或视频。
