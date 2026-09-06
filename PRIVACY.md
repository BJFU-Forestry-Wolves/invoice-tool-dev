# 隐私数据隔离规则

## 目录边界

- `invoice-tool-dev/` 是唯一 Git 仓库，只保存源码、测试、构建配置和脱敏文档。
- `../附件/` 保存报销附件，不属于 Git 工作树。
- `../本地测试数据/` 保存真实冒烟清单与 OCR 输出，不属于 Git 工作树。
- CSV 和 Excel 文件必须保存在 Git 仓库外，例如工作区根目录或单独的数据目录。

## 提交保护

仓库 `.gitignore` 额外拒绝 CSV、Excel、PDF、常见图片和 OCR 结果文件。真实输入清单不得复制进仓库；需要运行 P0 冒烟时，显式传入仓库外清单：

```powershell
.\.ocr-venv\Scripts\python.exe .\p0_ocr_smoke.py --manifest ..\本地测试数据\p0-smoke-manifest.json
```

提交前至少执行：

```powershell
python scripts/privacy_check.py --scope all
python scripts/privacy_check.py --scope history
git status --short
git diff --cached --name-only
```

仓库通过 `core.hooksPath=.githooks` 启用提交钩子。钩子会阻止上述敏感文件类型及疑似真实 BX 编号进入新提交。
