# 报销附件整理与订单日期识别工具

面向 Windows 的离线报销附件整理工具，可批量匹配和重命名发票/订单截图，使用 PaddleOCR 提取下单日期与发票销售方，并生成 Excel 复核报告。

> OCR 结果用于辅助整理，不能代替人工财务审核。真实报销数据应始终存放在源码仓库之外。

## 功能

- 根据 CSV 数据表匹配、复制和重命名附件
- 从 JPG、JPEG、PNG、BMP、PDF 中识别订单日期
- 排除付款、发货、收货、退款和开票日期
- 使用 SQLite 和文件哈希进行增量识别
- 识别发票销售方并按可配置单日限额汇总
- 按日期、人员和异常状态生成分类计划
- 输出 Excel 汇总、识别明细、待复核项和运行统计

## 快速开始

Windows Release 用户解压程序包后运行 `invoice_attachment_tool.exe`。首次使用 OCR 时点击“一键获取模型”，程序默认从本仓库的 `models-v1` Release 下载，失败后尝试配置的镜像。

源码运行要求 Python 3.11：

```powershell
python -m venv .ocr-venv
.\.ocr-venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
.\.ocr-venv\Scripts\python.exe invoice_attachment_gui.py
```

## 输入目录

```text
附件根目录/
├─ 发票/
└─ 订单截图/
```

附件使用 `BX` 加数字的业务编号命名，例如 `BX0001.pdf`、`BX0001(1).png`。CSV 至少应提供编号、上传人、用途、税后金额、发票和订单截图字段。

## 界面预览

公开前可将不含真实姓名、编号、金额和路径的截图保存为 `docs/images/app.png`，再在这里补充图片链接。

## 命令行

```powershell
python rename_invoices_orders.py --csv <数据.csv> --attach-root <附件目录> --output-dir <输出目录> --dry-run
python order_date_report_cli.py --csv <数据.csv> --attach-root <附件目录> --output-dir <输出目录>
python model_manager_cli.py status
python model_manager_cli.py download --source auto
python model_manager_cli.py verify
```

开票方和通用分类：

```powershell
python invoice_issuer_cli.py --manifest <分类清单.json> --attach-root <附件目录> --output-dir <输出目录> --daily-limit 1000
python classify_attachments.py --workbook <主工作簿.xlsx> --attach-root <附件目录> --rules-json <规则结果.json> --manual-labels <人工标注.xlsx> --reference-dir <更新附件目录> --output-dir <分类目录> --invoice-only-threshold 200 --dry-run
```

## 文件名模板

默认模板为 `{编号}_{上传人}_{用途}_{金额}_{附件标记}`。还可使用 `{下单日期}`、`{附件类型}`、`{序号}` 和 `{总数}`。建议保留 `{编号}` 与 `{附件标记}` 以避免重名。

## 模型与隐私

- 模型默认安装在 `%LOCALAPPDATA%\InvoiceAttachmentTool\models`，不进入 Git。
- 下载包和安装文件均通过 SHA-256 校验，安装失败不会覆盖已有可用模型。
- 模型源配置见 `config/release.json`，镜像也可通过 `INVOICE_TOOL_MODEL_MIRROR` 设置。
- CSV、Excel、PDF、图片、OCR JSON 和 SQLite 缓存均被 `.gitignore` 排除。
- 提交前运行 `python scripts/privacy_check.py --scope all` 和 `--scope history`。

## 开发

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
.\build.ps1
```

构建采用 PyInstaller `onedir`；模型作为独立 Release 资源分发，不嵌入程序。

## 限制

- 主要支持 Windows 10/11 x64。
- 模型路径应避免中文字符，以兼容 Paddle 静态推理。
- OCR 准确率受截图清晰度、平台版式和分辨率影响，异常状态必须人工复核。
- 输出目录和缓存目录必须位于 Git 仓库外。

许可证见 [LICENSE](LICENSE)，第三方说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
