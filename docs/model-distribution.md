# 模型分发

模型不进入 Git。应用根据 `models/manifest.json` 校验模型，根据 `config/release.json` 生成下载地址。

## 生成模型包

```powershell
python scripts/package_models.py `
  --models-dir "$env:LOCALAPPDATA\InvoiceAttachmentTool\models" `
  --output-dir "..\model-release-assets" `
  --update-manifest
```

工具会在仓库外生成模型 ZIP、SHA256、更新后的清单副本和 `UPLOAD.txt`。压缩包固定包含 `official_models/<模型名>/...`。

## GitHub Release

1. 创建标签为 `models-v1` 的 Release。
2. 上传 `ppocrv6-medium-models-v1.zip` 及其 `.sha256`。
3. 确认 `config/release.json` 的仓库名正确。
4. 运行 `python model_manager_cli.py download --source github` 验证。

## 镜像

镜像根地址下放置同名 ZIP。可填写 `mirror_base_url`，或设置环境变量：

```powershell
$env:INVOICE_TOOL_MODEL_MIRROR = "https://mirror.example.com/invoice-tool/models-v1"
```

`auto` 模式按 GitHub、镜像顺序尝试，任何来源都必须通过清单中的 SHA-256 校验。
