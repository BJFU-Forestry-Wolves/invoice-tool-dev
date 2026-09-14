# 智能发票整理工具

一款面向 Windows 的本地发票与订单附件整理工具。它可以批量匹配附件、统一文件名，并通过 OCR 提取订单日期和发票销售方，最后生成便于人工复核的 Excel 报告。

所有业务文件默认只在本机处理。项目不会上传发票、订单截图或报销表格；只有在用户明确点击“一键获取模型”时，程序才会联网下载 OCR 模型。

## 主要功能

- 按业务编号匹配发票和订单截图
- 批量复制、分类并统一附件文件名
- 从图片和 PDF 中识别订单下单日期
- 识别发票销售方，按单日限额汇总
- 缓存已经完成的 OCR 结果，避免重复识别
- 输出识别明细、汇总结果和待人工复核项
- 在应用内检查、下载和校验 OCR 模型

支持 JPG、JPEG、PNG、BMP 和 PDF 附件。

## 下载与使用

### 下载 Windows 版本

1. 打开项目的 [Releases 页面](https://github.com/BJFU-Forestry-Wolves/invoice-tool-dev/releases)。
2. 下载最新版本中的 `invoice_attachment_tool-windows-x64.zip`。
3. 解压到一个独立目录，不要直接在压缩包内运行。
4. 双击 `invoice_attachment_tool.exe`。
5. 第一次使用 OCR 时，在程序中点击 **一键获取模型**。

程序支持 Windows 10/11 x64。OCR 模型单独发布，因此升级应用时通常不需要重新下载模型。

### 从源码运行

需要 Python 3.11：

```powershell
git clone https://github.com/BJFU-Forestry-Wolves/invoice-tool-dev.git
cd invoice-tool-dev
python -m venv .ocr-venv
.\.ocr-venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
.\.ocr-venv\Scripts\python.exe invoice_attachment_gui.py
```

## 基本使用流程

1. 准备数据表、发票目录和订单截图目录。
2. 打开程序，选择数据表、附件根目录和输出目录。
3. 选择需要执行的任务，并先进行预演检查。
4. 确认匹配结果无误后，再执行正式整理。
5. 打开输出目录，检查 Excel 报告中的待复核项目。

推荐的附件目录结构：

```text
附件根目录/
├─ 发票/
└─ 订单截图/
```

附件名中需要包含可用于匹配的业务编号，例如 `BX0001.pdf`、`BX0001(1).png`。数据表至少需要提供编号、上传人、用途、金额以及附件数量等信息。

> OCR 结果只用于辅助整理，不能替代人工财务审核。正式归档前请检查待复核项目和汇总金额。

## OCR 模型

程序包不内置约 146 MB 的 OCR 模型。首次使用时可以直接在界面中选择下载来源：

- **自动**：先尝试 GitHub Release，失败后尝试已配置的镜像
- **GitHub**：只从本项目的模型 Release 下载
- **镜像**：只从维护者配置的镜像下载

模型会安装到 `%LOCALAPPDATA%\InvoiceAttachmentTool\models`。下载和安装过程会校验 SHA-256；安装失败不会覆盖原有的可用模型。

也可以通过命令行管理模型：

```powershell
python model_manager_cli.py status
python model_manager_cli.py download --source auto
python model_manager_cli.py verify
```

模型发布和镜像配置说明见 [docs/model-distribution.md](docs/model-distribution.md)。

## 文件名模板

默认模板为：

```text
{编号}_{上传人}_{用途}_{金额}_{附件标记}
```

还可以使用 `{下单日期}`、`{附件类型}`、`{序号}` 和 `{总数}`。建议始终保留 `{编号}` 与 `{附件标记}`，避免不同附件生成相同文件名。

## 命令行工具

普通用户建议使用图形界面。以下入口适合批处理和二次开发：

```powershell
# 匹配和整理附件
python rename_invoices_orders.py --csv <数据.csv> --attach-root <附件目录> --output-dir <输出目录> --dry-run

# 识别订单日期并生成报告
python order_date_report_cli.py --csv <数据.csv> --attach-root <附件目录> --output-dir <输出目录>

# 识别发票销售方并设置单日限额
python invoice_issuer_cli.py --manifest <分类清单.json> --attach-root <附件目录> --output-dir <输出目录> --daily-limit 1000

# 生成通用分类计划
python classify_attachments.py --workbook <数据.xlsx> --attach-root <附件目录> --rules-json <规则结果.json> --manual-labels <人工标注.xlsx> --reference-dir <参考附件目录> --output-dir <分类目录> --invoice-only-threshold 200 --dry-run
```

正式执行前建议保留 `--dry-run`，先检查计划结果。

## 数据安全与隐私

- CSV、Excel、PDF、图片、OCR 结果和缓存文件默认不会进入 Git
- 输出目录和真实业务数据应放在源码仓库之外
- 项目提供提交前隐私扫描，检查身份证号、手机号、银行卡号、密钥、本机用户路径等内容
- 如发现安全问题，请不要公开提交 Issue，处理方式见 [SECURITY.md](SECURITY.md)

隐私扫描命令：

```powershell
python scripts/privacy_check.py --scope all
python scripts/privacy_check.py --scope history
```

## 已知限制

- OCR 准确率会受到截图清晰度、平台版式和图片分辨率影响
- 模糊、裁切不完整或包含多个日期的附件可能需要人工确认
- 为兼容部分 Paddle 推理组件，模型安装路径应尽量避免中文字符
- 当前发布流程主要面向 Windows 10/11 x64

## 开发与构建

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
.\build.ps1
```

Windows 发布包使用 PyInstaller `onedir` 构建。推送 `v*` 标签后，GitHub Actions 会自动生成应用 ZIP 和 SHA-256 校验文件；OCR 模型通过独立的 `models-v1` Release 分发。

参与开发前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。版本变化见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

项目代码采用 [MIT License](LICENSE)。PaddleOCR 等第三方组件和模型遵循各自许可证，详情见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
