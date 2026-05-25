# Install Board Sync + Web Dashboard v4

ACE SIGN 安装日程管理系统。从 Production Board 自动同步到 Install Board，并生成网页仪表盘。

## 功能

- ✅ 自动同步 Production Board → Install Board（每 2 小时）
- ✅ Sign Proof PDF 自动转 JPG，网页直接显示
- ✅ Outlook 风格周视图（Group A / Group B 双列并排）
- ✅ 日视图 / 列表视图 / 地图视图
- ✅ 按 priority、team、installer 过滤
- ✅ PDF 导出（周/日）
- ✅ 密码保护

## 网址

https://1131910095b.github.io/install-board-sync/

密码：`ace2026`

## 文件说明

```
install-board-sync/
├── install-sync.py              Production Board → Install Board 同步
├── data-export.py               Install Board → docs/data.json
├── proof-export.py              Sign Proof PDF → JPG
├── .github/workflows/
│   └── install-sync.yml         GitHub Actions（每 2 小时跑一次）
└── docs/                        GitHub Pages 网站
    └── index.html               主页面（Outlook 周视图）
```

## GitHub Secrets 配置

需要在仓库 Settings → Secrets and variables → Actions 配置：

- `MONDAY_API_TOKEN`

## Install Board 列结构

- `date_mm3mqpzy`  Install Date
- `long_text_mm3mbfg4`  Address
- `dropdown_mm3mbcf8`  Installer (Peter, Chris, Kent, Daniel, Dani)
- `color_mm3mc33r`  Schedule Status
- `dropdown_mm3m3ngw`  Project Type (Pick Up / Delivery / Install)
- `color_mm3mpe1m`  Priority (Urgent / High / Medium / Low)
- `numeric_mm3mxrbf`  Installation Value
- `dropdown_mm3mgx76`  Sales (Chike, Harry, Barry, Fiona, Rex, Jenny, Jack)
- `long_text_mm3mq5tb`  Notes
- `board_relation_mm3mj5j8`  Production Project (link to Production Board)
- `color_mm3matf`  Team (Group A / Group B)  **v4 新增**
- `numeric_mm3mk5em`  Duration (hrs)  **v4 新增**

## GitHub Actions 工作流

每 2 小时自动跑一次：

1. `install-sync.py` —— 从 Production Board 同步到 Install Board
2. `data-export.py` —— 把 Install Board 数据导出到 `docs/data.json`
3. `proof-export.py` —— 把 Sign Proof PDF 转成 JPG 存到 `docs/proofs/`
4. 提交所有变更到仓库

## 手动触发

GitHub → Actions → "Install Board Sync" → Run workflow
