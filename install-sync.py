"""
Production Board → Install Board 同步脚本

逻辑：
- 拉 Production Board 上所有 Install Date 在 [今天-30天, 未来不限] 范围内的项目
- 在 Install Board 创建/更新对应项目（按 production_item_id 匹配，不重复）
- 同步字段：Install Date, Address, Project Type, Priority, Installation Value, Sales
- 不动 Installer / Schedule Status / Notes（让调度员手动管理）
- 自动连接 Production Board
"""
import os
import time
import json
import datetime as dt
from typing import Any, Dict, List, Optional

import requests

# ============ 配置 ============
MONDAY_API_TOKEN = os.environ["MONDAY_API_TOKEN"]

PRODUCTION_BOARD_ID = "2053705854"
INSTALL_BOARD_ID = "5028736896"

# Production Board 列
PROD = {
    "install_date": "date_mm1dqz30",
    "address": "long_text_mktqgmm7",
    "project_status": "dropdown_mktv4twn",  # Pick Up/Delivery/Install
    "priority": "color_mkthx5tn",  # Urgent/High/Medium/Low/Waiting/NO IN HOUSE JOB
    "installation_value": "numeric_mktj9emh",
    "sales": "dropdown_mkthwawn",
    "status": "status",  # 主状态：Design/Production/Installation/Job Completed!/Finished 等
}

# Install Board 列
INST = {
    "install_date": "date_mm3mqpzy",
    "address": "long_text_mm3mbfg4",
    "installer": "dropdown_mm3mbcf8",  # 不同步，留给调度员
    "schedule_status": "color_mm3mc33r",  # 不同步，独立
    "project_type": "dropdown_mm3m3ngw",  # Pick Up/Delivery/Install
    "priority": "color_mm3mpe1m",  # Urgent/High/Medium/Low
    "installation_value": "numeric_mm3mxrbf",
    "sales": "dropdown_mm3mgx76",
    "notes": "long_text_mm3mq5tb",  # 不同步
    "production_link": "board_relation_mm3mj5j8",
}

# 同步范围：过去 30 天 + 未来全部
DAYS_BACK = 30


def log(msg: str) -> None:
    print(f"[{dt.datetime.utcnow().isoformat()}] {msg}", flush=True)


# ============ 重试 ============
RETRY_STATUS = {429, 502, 503, 504}
MAX_RETRIES = 4


def request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.request(method, url, **kwargs)
            if r.status_code in RETRY_STATUS and attempt < MAX_RETRIES:
                wait = 2 ** attempt * 5
                log(f"  ⚠ HTTP {r.status_code}，{wait}s 后重试 ({attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt * 5
                log(f"  ⚠ 网络错误 {type(e).__name__}，{wait}s 后重试 ({attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            raise
    if last_exc:
        raise last_exc
    return r  # type: ignore


def monday_query(query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
    r = request_with_retry(
        "POST",
        "https://api.monday.com/v2",
        headers={
            "Authorization": MONDAY_API_TOKEN,
            "Content-Type": "application/json",
            "API-Version": "2024-01",
        },
        json={"query": query, "variables": variables or {}},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(f"monday GraphQL error: {data['errors']}")
    return data["data"]


# ============ 从 Production 拉数据 ============
def fetch_production_items_with_install_date() -> List[Dict[str, Any]]:
    """
    拉 Production Board 所有有 Install Date 的项目。
    返回 [{id, name, install_date, address, project_status, priority, value, sales, status}]
    """
    log("从 Production Board 拉取项目...")
    items = []
    cursor: Optional[str] = None
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=DAYS_BACK)

    column_ids = [
        PROD["install_date"], PROD["address"], PROD["project_status"],
        PROD["priority"], PROD["installation_value"], PROD["sales"], PROD["status"],
    ]
    col_ids_str = json.dumps(column_ids)

    while True:
        if cursor:
            query = f"""
            query ($cursor: String!) {{
              boards(ids: [{PROD_BOARD_INT}]) {{
                items_page(limit: 200, cursor: $cursor) {{
                  cursor
                  items {{
                    id
                    name
                    column_values(ids: {col_ids_str}) {{ id text }}
                  }}
                }}
              }}
            }}
            """
            vars_ = {"cursor": cursor}
        else:
            query = f"""
            query {{
              boards(ids: [{PROD_BOARD_INT}]) {{
                items_page(limit: 200) {{
                  cursor
                  items {{
                    id
                    name
                    column_values(ids: {col_ids_str}) {{ id text }}
                  }}
                }}
              }}
            }}
            """
            vars_ = {}
        data = monday_query(query, vars_)
        page = data["boards"][0]["items_page"]
        for item in page["items"]:
            vals = {cv["id"]: cv.get("text") for cv in item.get("column_values", [])}
            install_date_str = vals.get(PROD["install_date"])
            if not install_date_str:
                continue
            try:
                install_date = dt.datetime.strptime(install_date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            if install_date < cutoff:
                continue
            items.append({
                "id": item["id"],
                "name": item["name"],
                "install_date": install_date_str,
                "address": vals.get(PROD["address"]) or "",
                "project_status": vals.get(PROD["project_status"]) or "",
                "priority": vals.get(PROD["priority"]) or "",
                "installation_value": vals.get(PROD["installation_value"]) or "",
                "sales": vals.get(PROD["sales"]) or "",
                "production_status": vals.get(PROD["status"]) or "",
            })
        cursor = page.get("cursor")
        if not cursor:
            break
    log(f"  找到 {len(items)} 个有 Install Date 的 Production 项目")
    return items


PROD_BOARD_INT = int(PRODUCTION_BOARD_ID)


# ============ 读取已存在的 Install Board 项目 ============
def fetch_install_board_items() -> Dict[str, str]:
    """
    返回 {production_item_id: install_item_id}
    通过 Production Project (board_relation) 列匹配
    """
    log("读取 Install Board 已有项目...")
    mapping: Dict[str, str] = {}
    cursor: Optional[str] = None

    while True:
        if cursor:
            query = f"""
            query ($cursor: String!) {{
              boards(ids: [{int(INSTALL_BOARD_ID)}]) {{
                items_page(limit: 500, cursor: $cursor) {{
                  cursor
                  items {{
                    id
                    column_values(ids: ["{INST['production_link']}"]) {{
                      ... on BoardRelationValue {{
                        linked_item_ids
                      }}
                    }}
                  }}
                }}
              }}
            }}
            """
            vars_ = {"cursor": cursor}
        else:
            query = f"""
            query {{
              boards(ids: [{int(INSTALL_BOARD_ID)}]) {{
                items_page(limit: 500) {{
                  cursor
                  items {{
                    id
                    column_values(ids: ["{INST['production_link']}"]) {{
                      ... on BoardRelationValue {{
                        linked_item_ids
                      }}
                    }}
                  }}
                }}
              }}
            }}
            """
            vars_ = {}
        data = monday_query(query, vars_)
        page = data["boards"][0]["items_page"]
        for item in page["items"]:
            cvs = item.get("column_values", [])
            if cvs and cvs[0].get("linked_item_ids"):
                for prod_id in cvs[0]["linked_item_ids"]:
                    mapping[str(prod_id)] = item["id"]
        cursor = page.get("cursor")
        if not cursor:
            break
    log(f"  Install Board 已有 {len(mapping)} 个映射")
    return mapping


# ============ 字段值转换 ============
def project_type_from_production(value: str) -> Optional[str]:
    """Production 的 Project Status dropdown 值 → Install Board 的 Project Type"""
    if not value:
        return None
    # 直接取第一个匹配的：Pick Up / Delivery / Install
    for option in ["Pick Up", "Delivery", "Install"]:
        if option in value:
            return option
    return None


def priority_from_production(value: str) -> Optional[str]:
    """Production Priority → Install Board Priority"""
    if not value:
        return None
    if "Urgent" in value:
        return "Urgent"
    if "High" in value:
        return "High"
    if "Medium" in value:
        return "Medium"
    if "Low" in value:
        return "Low"
    return None


def build_install_column_values(prod_item: Dict[str, Any]) -> Dict[str, Any]:
    cv: Dict[str, Any] = {
        INST["install_date"]: {"date": prod_item["install_date"]},
        INST["address"]: prod_item["address"],
        INST["production_link"]: {"item_ids": [int(prod_item["id"])]},
    }

    # Project Type
    pt = project_type_from_production(prod_item["project_status"])
    if pt:
        cv[INST["project_type"]] = {"labels": [pt]}

    # Priority
    pr = priority_from_production(prod_item["priority"])
    if pr:
        cv[INST["priority"]] = {"label": pr}

    # Installation Value
    if prod_item["installation_value"]:
        try:
            cv[INST["installation_value"]] = float(prod_item["installation_value"])
        except ValueError:
            pass

    # Sales
    if prod_item["sales"]:
        # 取第一个销售
        sales_first = prod_item["sales"].split(",")[0].strip()
        if sales_first:
            cv[INST["sales"]] = {"labels": [sales_first]}

    return cv


# ============ 创建/更新 ============
def create_install_item(prod_item: Dict[str, Any]) -> str:
    cv = build_install_column_values(prod_item)
    data = monday_query(
        """
        mutation ($board: ID!, $name: String!, $values: JSON!) {
          create_item(
            board_id: $board,
            item_name: $name,
            column_values: $values,
            create_labels_if_missing: true
          ) { id }
        }
        """,
        {"board": INSTALL_BOARD_ID, "name": prod_item["name"], "values": json.dumps(cv)},
    )
    return data["create_item"]["id"]


def update_install_item(install_item_id: str, prod_item: Dict[str, Any]) -> None:
    cv = build_install_column_values(prod_item)
    # 更新时不再写 production_link（避免覆盖）和 priority/project_type（避免覆盖手动修改）
    # 但 install_date / address / value 应该跟 Production 保持一致
    update_cv = {
        INST["install_date"]: cv[INST["install_date"]],
        INST["address"]: cv[INST["address"]],
    }
    if INST["installation_value"] in cv:
        update_cv[INST["installation_value"]] = cv[INST["installation_value"]]

    monday_query(
        """
        mutation ($board: ID!, $item: ID!, $values: JSON!) {
          change_multiple_column_values(
            board_id: $board, item_id: $item, column_values: $values
          ) { id }
        }
        """,
        {"board": INSTALL_BOARD_ID, "item": install_item_id, "values": json.dumps(update_cv)},
    )


# ============ 主流程 ============
def main() -> None:
    log("开始同步 Production → Install Board")
    prod_items = fetch_production_items_with_install_date()
    existing_mapping = fetch_install_board_items()

    created = 0
    updated = 0
    failed = 0

    for prod_item in prod_items:
        try:
            if prod_item["id"] in existing_mapping:
                install_id = existing_mapping[prod_item["id"]]
                update_install_item(install_id, prod_item)
                updated += 1
            else:
                create_install_item(prod_item)
                created += 1
        except Exception as e:
            failed += 1
            log(f"  ✗ {prod_item['name']} 失败: {e}")

    log(f"完成 ✓ 创建 {created}，更新 {updated}，失败 {failed}")


if __name__ == "__main__":
    main()
