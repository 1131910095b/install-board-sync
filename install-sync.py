"""
Install Board Sync v5
从 Production Board 同步到 Install Board

v5 新增字段:
- Project Manager (Producer 列)
- Planned Hours (plan hours 列)
- Status (Pre-Installation / Installation 等)
"""
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

MONDAY_API_TOKEN = os.environ["MONDAY_API_TOKEN"]

PROD_BOARD_ID = "2053705854"
INSTALL_BOARD_ID = "5028736896"

PROD_COL = {
    "install_date": "date_mm1dqz30",
    "address": "long_text_mktqgmm7",
    "installer": "dropdown_mkthh4y1",
    "sales": "dropdown_mkthwawn",
    "priority": "color_mkthx5tn",
    "project_type": "dropdown_mktv4twn",
    "installation_value": "numeric_mktj9emh",
    "invoice_number": "text_mkthyz6",
    "producer": "dropdown_mkthvkf5",
    "plan_hours": "text_mm3pfqy5",
    "status": "status",
    "install_board_link": "board_relation_mm3mmcjn",
}

INSTALL_COL = {
    "install_date": "date_mm3mqpzy",
    "address": "long_text_mm3mbfg4",
    "installer": "dropdown_mm3mbcf8",
    "schedule_status": "color_mm3mc33r",
    "project_type": "dropdown_mm3m3ngw",
    "priority": "color_mm3mpe1m",
    "installation_value": "numeric_mm3mxrbf",
    "sales": "dropdown_mm3mgx76",
    "notes": "long_text_mm3mq5tb",
    "production_link": "board_relation_mm3mj5j8",
    "team": "color_mm3matf",
    "duration_hours": "numeric_mm3mk5em",
}

# Priority label mapping (Production -> Install)
PRIORITY_MAP = {
    "Urgent ⚠️️": "Urgent",
    "High": "High",
    "Medium": "Medium",
    "Low": "Low",
}


def log(msg: str) -> None:
    print(f"[{datetime.utcnow().isoformat()}] {msg}", flush=True)


def monday_query(query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
    r = requests.post(
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


def fetch_production_items() -> List[Dict[str, Any]]:
    """Fetch all Production items that have an install_date within 30 days back to unlimited future."""
    log("读取 Production Board...")
    items: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    cols = json.dumps(list(PROD_COL.values()))
    while True:
        if cursor:
            q = f"""
            query ($board: ID!, $cursor: String!) {{
              boards(ids: [$board]) {{
                items_page(limit: 200, cursor: $cursor) {{
                  cursor
                  items {{
                    id name
                    column_values(ids: {cols}) {{ id text value }}
                  }}
                }}
              }}
            }}"""
            vars_ = {"board": PROD_BOARD_ID, "cursor": cursor}
        else:
            q = f"""
            query ($board: ID!) {{
              boards(ids: [$board]) {{
                items_page(limit: 200) {{
                  cursor
                  items {{
                    id name
                    column_values(ids: {cols}) {{ id text value }}
                  }}
                }}
              }}
            }}"""
            vars_ = {"board": PROD_BOARD_ID}
        data = monday_query(q, vars_)
        page = data["boards"][0]["items_page"]
        items.extend(page["items"])
        cursor = page.get("cursor")
        if not cursor:
            break
    log(f"Production Board 共 {len(items)} 个项目")
    return items


def fetch_install_items() -> Dict[str, str]:
    """Map production_id -> install_item_id by reading the production_link column."""
    log("读取 Install Board 现有项目...")
    existing: Dict[str, str] = {}
    cursor: Optional[str] = None
    while True:
        if cursor:
            q = """
            query ($board: ID!, $cursor: String!) {
              boards(ids: [$board]) {
                items_page(limit: 200, cursor: $cursor) {
                  cursor
                  items {
                    id name
                    column_values(ids: ["board_relation_mm3mj5j8"]) { value }
                  }
                }
              }
            }"""
            vars_ = {"board": INSTALL_BOARD_ID, "cursor": cursor}
        else:
            q = """
            query ($board: ID!) {
              boards(ids: [$board]) {
                items_page(limit: 200) {
                  cursor
                  items {
                    id name
                    column_values(ids: ["board_relation_mm3mj5j8"]) { value }
                  }
                }
              }
            }"""
            vars_ = {"board": INSTALL_BOARD_ID}
        data = monday_query(q, vars_)
        page = data["boards"][0]["items_page"]
        for item in page["items"]:
            cv = item["column_values"][0] if item["column_values"] else None
            if not cv or not cv.get("value"):
                continue
            try:
                v = json.loads(cv["value"])
                prod_ids = v.get("linkedPulseIds") or []
                if prod_ids:
                    pid = str(prod_ids[0].get("linkedPulseId"))
                    existing[pid] = item["id"]
            except Exception:
                pass
        cursor = page.get("cursor")
        if not cursor:
            break
    log(f"Install Board 共 {len(existing)} 个已链接项目")
    return existing


def parse_prod(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    cv_map = {cv["id"]: cv for cv in item.get("column_values", [])}

    def text_of(col_id: str) -> str:
        cv = cv_map.get(col_id)
        return (cv.get("text") or "").strip() if cv else ""

    install_date = text_of(PROD_COL["install_date"])
    if not install_date:
        return None

    # Only sync items within 30 days back to future
    try:
        d = datetime.strptime(install_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    cutoff = datetime.utcnow().date() - timedelta(days=30)
    if d < cutoff:
        return None

    return {
        "prod_id": item["id"],
        "name": item["name"],
        "install_date": install_date,
        "address": text_of(PROD_COL["address"]),
        "installer": text_of(PROD_COL["installer"]),
        "sales": text_of(PROD_COL["sales"]),
        "priority": text_of(PROD_COL["priority"]),
        "project_type": text_of(PROD_COL["project_type"]),
        "installation_value": text_of(PROD_COL["installation_value"]),
        "invoice_number": text_of(PROD_COL["invoice_number"]),
        "producer": text_of(PROD_COL["producer"]),
        "plan_hours": text_of(PROD_COL["plan_hours"]),
        "status": text_of(PROD_COL["status"]),
    }


def to_install_column_values(p: Dict[str, Any]) -> Dict[str, Any]:
    cv: Dict[str, Any] = {
        INSTALL_COL["install_date"]: {"date": p["install_date"]} if p["install_date"] else None,
        INSTALL_COL["address"]: p["address"],
        INSTALL_COL["production_link"]: {"item_ids": [int(p["prod_id"])]},
    }
    if p["installer"]:
        cv[INSTALL_COL["installer"]] = {"labels": [s.strip() for s in p["installer"].split(",") if s.strip()]}
    if p["sales"]:
        cv[INSTALL_COL["sales"]] = {"labels": [s.strip() for s in p["sales"].split(",") if s.strip()]}
    if p["project_type"]:
        cv[INSTALL_COL["project_type"]] = {"labels": [s.strip() for s in p["project_type"].split(",") if s.strip()]}
    if p["priority"]:
        mapped = PRIORITY_MAP.get(p["priority"], p["priority"])
        cv[INSTALL_COL["priority"]] = {"label": mapped}
    if p["installation_value"]:
        try:
            cv[INSTALL_COL["installation_value"]] = float(p["installation_value"])
        except (ValueError, TypeError):
            pass
    if p["plan_hours"]:
        try:
            cv[INSTALL_COL["duration_hours"]] = float(p["plan_hours"])
        except (ValueError, TypeError):
            pass
    # Remove nulls
    cv = {k: v for k, v in cv.items() if v is not None}
    return cv


def create_install_item(p: Dict[str, Any]) -> str:
    cv = to_install_column_values(p)
    data = monday_query(
        """
        mutation ($board: ID!, $name: String!, $cv: JSON!) {
          create_item(board_id: $board, item_name: $name, column_values: $cv) { id }
        }""",
        {"board": INSTALL_BOARD_ID, "name": p["name"], "cv": json.dumps(cv)},
    )
    return data["create_item"]["id"]


def update_install_item(item_id: str, p: Dict[str, Any]) -> None:
    cv = to_install_column_values(p)
    monday_query(
        """
        mutation ($board: ID!, $item: ID!, $cv: JSON!) {
          change_multiple_column_values(board_id: $board, item_id: $item, column_values: $cv) { id }
        }""",
        {"board": INSTALL_BOARD_ID, "item": item_id, "cv": json.dumps(cv)},
    )


def main() -> None:
    log("开始同步 Production → Install Board")
    prod_items = fetch_production_items()
    existing = fetch_install_items()

    created = 0
    updated = 0
    skipped = 0
    failed = 0

    for item in prod_items:
        p = parse_prod(item)
        if not p:
            skipped += 1
            continue
        try:
            if p["prod_id"] in existing:
                update_install_item(existing[p["prod_id"]], p)
                updated += 1
            else:
                create_install_item(p)
                created += 1
        except Exception as e:
            failed += 1
            log(f"  ✗ {p['name']} 失败: {e}")

    log(f"完成 ✓ 创建 {created}，更新 {updated}，跳过 {skipped}，失败 {failed}")


if __name__ == "__main__":
    main()
