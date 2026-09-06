# 贡献指南

1. 使用 Python 3.11 创建虚拟环境并安装 `requirements-dev.txt`。
2. 只使用合成的 `DEMO` 编号、虚构名称和生成的图片编写测试。
3. 运行 `python scripts/privacy_check.py --scope all`。
4. 运行 `python -m pytest -q`。
5. 提交应说明行为变化、测试结果和兼容性影响。

模型、真实附件、缓存和输出报告不得进入提交。
