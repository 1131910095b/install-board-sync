# Install Board Sync + Web Dashboard v5

ACE SIGN 安装日程管理系统 - 完整版

## 网址

https://1131910095b.github.io/install-board-sync/

密码：`ace2026`

## v5 新功能

- ✅ 从 Production Board 同步更多字段（Project Manager / Planned Hours / Status / Project Type）
- ✅ **拖拽改日期** —— 拖工作卡片到不同日期，自动提交 GitHub Issue，下次 sync 时写回 monday
- ✅ **All Installs / Active 视图切换** —— Active 只显示 Pre-Installation 和 Installation 状态
- ✅ **按 Project Type 过滤** —— Install / Pick Up / Delivery
- ✅ **地图换 Carto Voyager** —— 比之前的 OSM 好看，只显示 Install 类型
- ✅ **每日 PDF** —— 按工单样式（Team A: Chris & Peter 表格）生成，包含 Sign Proof 图片
- ✅ **本地编辑** —— Team / Installer / Vehicle / Important Level / Notes 在网页里改，存浏览器

## ⚠️ 部署前必读：GitHub Token

要让拖拽改日期生效，你需要：

1. 创建一个 fine-grained GitHub PAT：
   - 去 https://github.com/settings/personal-access-tokens/new
   - Name: `install-board-issues`
   - Expiration: No expiration（或一年）
   - Repository access: Only select repositories → `install-board-sync`
   - Permissions → Repository → **Issues: Read and write**（其他全 No access）
   - Generate token, 复制下来

2. 把 token 粘贴到 `docs/index.html` 里：
   - 找到 `const GH_TOKEN = '';`
   - 改成 `const GH_TOKEN = 'github_pat_xxxxx';`

3. 还要把 token 设置成 GitHub Secret（用于 issue-processor.py）：
   - 仓库 Settings → Secrets and variables → Actions → New repository secret
   - Name: `GH_TOKEN`（如果默认的 `GITHUB_TOKEN` 不够权限）
   - 实际上 `${{ secrets.GITHUB_TOKEN }}` 默认就够用，不需要额外设置

## 文件结构

```
install-board-sync/
├── install-sync.py              Production Board → Install Board
├── data-export.py               Install Board → docs/data.json (+merge prod fields)
├── proof-export.py              Sign Proof PDF → JPG
├── issue-processor.py           读 GitHub Issues 写 install_date 回 monday  ★ v5 新增
├── .github/workflows/
│   └── install-sync.yml         GitHub Actions（每 2 小时跑）
└── docs/
    └── index.html               完整 v5 网页
```

## 工作流程

每 2 小时（或手动触发 workflow）：

1. **issue-processor.py** —— 读取 open issues，把 `[DATE-CHANGE] <prod_id> <new_date>` 标题的 issue 处理后关闭
2. **install-sync.py** —— Production Board 同步到 Install Board
3. **data-export.py** —— 导出最新数据到 `docs/data.json`
4. **proof-export.py** —— PDF 转 JPG
5. Commit `docs/`

## monday 必需的字段

### Production Board (2053705854)
所有都已存在，无需创建。

### Install Board (5028736896)
所有都已存在，无需创建。

## Secrets 设置

GitHub → Settings → Secrets and variables → Actions：

- `MONDAY_API_TOKEN` —— monday API token

`GITHUB_TOKEN` 自动可用，不需要手动设置。

## 手动触发

GitHub Actions → "Install Board Sync" → Run workflow
