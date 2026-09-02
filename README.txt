Git仓库地址：
https://github.com/Acking646/adacode-agent

项目简介：
AdaCode-Agent 是一个自行实现的本地编程智能体。它通过 OpenAI 兼容接口调用大语言模型，但文件读写、命令执行、JSON 动作解析、多轮循环、错误处理、轨迹记录和上下文压缩均由本地代码完成；没有封装现成 agent 产品，也没有使用 agent 框架。

运行方式：
先安装依赖并设置环境变量 SILICONFLOW_API_KEY、OPENAI_BASE_URL。之后在项目根目录运行：

powershell -ExecutionPolicy Bypass -File scripts/start_web_local.ps1

浏览器打开 http://127.0.0.1:8787，点击“重置演示”和“运行”。若使用 Qwen SFT，可将 Qwen3-4B LoRA 通过远程 vLLM 启动，并用本地 http://127.0.0.1:8001/v1 访问。

特色功能：
智能体按“思考-动作-观察”循环工作，支持 list_files、read_file、edit_file、write_file、run_tests 等本地工具。核心设计是 AdaCom 启发的上下文管理器：每轮调用前，将任务、工具观察、失败测试、代码片段和结构化记忆转为候选上下文，再输出 keep/drop，压缩无关历史。系统内置规则管理器，也支持 Qwen3-4B LoRA SFT 管理器；第一轮无工具历史时只保留任务，后续保留最近动作和工具观察。

演示与实验：
内置演示改编自 QuixBugs 的 RPN_EVAL 缺陷。智能体会读取测试和实现，发现逆波兰表达式计算器把 left/right 操作数传反，自动修改代码并运行 pytest 验证。Web 控制台展示补丁、测试输出、上下文保留/丢弃和压缩率。初步实验：400-token 上下文选择中 F1 约 0.750、压缩率约 0.735；10 个 QuixBugs 子任务端到端预计通过 5/10，平均 5.8 步，延迟约 31.8 秒。


