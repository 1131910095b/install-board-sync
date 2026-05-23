# Install Board Sync + Web Dashboard v3

包含 Sign Proof PDF 自动同步显示。

## 功能
- Production Board → Install Board 自动同步
- Install Board → docs/data.json
- Production Board Sign Proof PDF → docs/proofs/{id}_pN.jpg
- 网页面板：日程视图 + 地图视图 + 项目详情 + PDF 下载

## 部署
1. GitHub Secrets: `MONDAY_API_TOKEN`
2. Settings → Pages: branch=main, folder=/docs
3. Settings → Actions → General → Workflow permissions: Read and write
4. Actions → Sync and Export → Run workflow

## 密码: ace2026

改密码：用 SHA-256 计算器生成新 hash，替换 docs/index.html 里的 `PASSWORD_HASH`。
