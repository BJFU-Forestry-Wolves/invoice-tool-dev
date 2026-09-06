# 安全与隐私

请勿在 Issue、Pull Request 或日志中提交真实发票、订单截图、报销编号、姓名、联系方式、银行信息或本机绝对路径。

业务输入、OCR 缓存和生成报告必须位于 Git 仓库外。提交前执行：

```powershell
python scripts/privacy_check.py --scope all
python scripts/privacy_check.py --scope history
git diff --cached --name-only
```

发现安全问题时，请通过仓库所有者配置的私密安全报告渠道联系维护者，不要公开披露包含真实业务数据的复现材料。
