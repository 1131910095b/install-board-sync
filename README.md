# Install Board Sync + Web Dashboard

一个综合系统：从 monday.com Production Board 同步安装项目到 Install Board，并提供网页面板查看安装日程、地图路线、PDF 下载。

## 架构

```
Production Board (monday)
    ↓ install-sync.py (每2小时)
Install Board (monday) - 调度员手动分配 Installer
    ↓ data-export.py (每2小时)
docs/data.json (静态 JSON)
    ↓ GitHub Pages
网页面板 - 看板/地图/PDF 下载
```

## 部署

### 1. GitHub Secrets
仓库 Settings → Secrets and variables → Actions：
- `MONDAY_API_TOKEN` — monday.com API token

### 2. 启用 GitHub Pages
仓库 Settings → Pages：
- Source: **Deploy from a branch**
- Branch: **main** / folder: **/docs**
- 保存

几分钟后，网页地址在 Pages 设置页显示，类似：
`https://1131910095b.github.io/install-board-sync/`

### 3. 手动跑一次 workflow
Actions tab → Sync and Export → Run workflow

跑完后 `docs/data.json` 会更新，网页就能加载数据了。

## 网页登录

**默认密码：`ace2026`**

改密码：
1. 用 SHA-256 计算器生成新密码的 hash（如 https://emn178.github.io/online-tools/sha256.html）
2. 改 `docs/index.html` 里 `PASSWORD_HASH` 这一行
3. Commit

## 功能

### 看板视图
- 按月份切换（默认当月）
- 按日期分组显示项目
- 优先级颜色标签
- 显示 Installer / Project Type / 价值 / 销售

### 地图视图
- 自动从地址转 GPS（OpenStreetMap Nominatim，免费）
- 按优先级颜色标记
- 点 marker 弹出详情 + Google Maps 导航链接
- 地理编码结果缓存到浏览器 localStorage（避免重复请求）

### PDF 下载
- 一键下载当月安装表
- 按日期分组，含地址、Installer、Notes
- A4 纵向，可直接打印

## 看板 ID
- Production Board: `2053705854`
- Install Board: `5028736896`

## 文件结构
```
install-board-sync/
├── install-sync.py          # Production → Install Board 同步
├── data-export.py           # Install Board → docs/data.json
├── docs/
│   ├── index.html           # 网页入口（GitHub Pages 根）
│   └── data.json            # 自动生成
└── .github/workflows/
    └── install-sync.yml     # 每 2 小时跑
```
