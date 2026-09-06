# GitHub 上传清单

## 只需修改一次

编辑 `config/release.json`：

```json
{
  "schema_version": 1,
  "github_repository": "你的账号/仓库名",
  "model_release_tag": "models-v1",
  "mirror_base_url": ""
}
```

## 上传前检查

```powershell
python scripts/privacy_check.py --scope all
python scripts/privacy_check.py --scope history
python -m pytest -q
git status --short
git diff --cached --name-only
```

## 推送与发布

```powershell
git remote add origin https://github.com/<账号>/<仓库>.git
git push -u origin main
gh release create models-v1 ..\model-release-assets\ppocrv6-medium-models-v1.zip ..\model-release-assets\ppocrv6-medium-models-v1.zip.sha256 --title "OCR Models v1"
git tag v0.1.0
git push origin v0.1.0
```

`v0.1.0` 标签会触发 Windows 程序构建和应用 Release。
