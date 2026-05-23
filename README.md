# Install Board Sync

从 monday.com 的 **Production Board** 自动同步有 Install Date 的项目到 **Install Board**。

## 配置

GitHub Secrets:
- `MONDAY_API_TOKEN` — monday.com API token

## 运行

- **自动**: 每 2 小时跑一次（cron `0 */2 * * *`）
- **手动**: Actions → Run install sync → Run workflow

## 同步逻辑

从 Production Board 拉取所有 Install Date 在 `[今天-30天, 未来]` 范围内的项目，
在 Install Board 上创建或更新对应项目。

### 同步字段（每次都更新）
- Install Date
- Address
- Installation Value

### 仅创建时同步（之后不动）
- Project Type (Pick Up / Delivery / Install)
- Priority (Urgent / High / Medium / Low)
- Sales

### 永不动（保留人工编辑）
- Installer（调度员手动分配）
- Schedule Status
- Notes

## 看板 ID

- Production Board: `2053705854`
- Install Board: `5028736896`
