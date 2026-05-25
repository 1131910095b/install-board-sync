"""
data-export.py v5
导出 Install Board + Production Board 数据到 docs/data.json

v5 新增:
- 通过 production_link 获取 Production Board 上的额外字段:
  Project Manager (Producer), Planned Hours, Status, Invoice Number
- 保留 Install Board 的本地字段: team, duration_hours (这些是本地调度数据)
"""
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

MONDAY_API_TOKEN = os.environ["MONDAY_API_TOKEN"]
INSTALL_BOARD_ID = "5028736896"
PROD_BOARD_ID = "2053705854"

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

PROD_COL = {
    "invoice_number": "text_mkthyz6",
    "producer": "dropdown_mkthvkf5",
    "plan_hours": "text_mm3pfqy5",
    "status": "status",
    "project_type": "dropdown_mktv4twn",
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


def fetch_install_items() -> List[Dict[str, Any]]:
    log("读取 Install Board...")
    items: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    cols = json.dumps(list(INSTALL_COL.values()))
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
            vars_ = {"board": INSTALL_BOARD_ID, "cursor": cursor}
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
            vars_ = {"board": INSTALL_BOARD_ID}
        data = monday_query(q, vars_)
        page = data["boards"][0]["items_page"]
        items.extend(page["items"])
        cursor = page.get("cursor")
        if not cursor:
            break
    log(f"Install Board 共 {len(items)} 项")
    return items


def fetch_prod_extra() -> Dict[str, Dict[str, str]]:
    """Fetch extra fields from Production Board: producer, plan_hours, invoice, status, project_type"""
    log("读取 Production Board 补充字段...")
    extra: Dict[str, Dict[str, str]] = {}
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
                    id
                    column_values(ids: {cols}) {{ id text }}
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
                    id
                    column_values(ids: {cols}) {{ id text }}
                  }}
                }}
              }}
            }}"""
            vars_ = {"board": PROD_BOARD_ID}
        data = monday_query(q, vars_)
        page = data["boards"][0]["items_page"]
        for item in page["items"]:
            cv_map = {cv["id"]: (cv.get("text") or "").strip() for cv in item.get("column_values", [])}
            extra[item["id"]] = {
                "invoice_number": cv_map.get(PROD_COL["invoice_number"], ""),
                "producer": cv_map.get(PROD_COL["producer"], ""),
                "plan_hours": cv_map.get(PROD_COL["plan_hours"], ""),
                "status": cv_map.get(PROD_COL["status"], ""),
                "project_type": cv_map.get(PROD_COL["project_type"], ""),
            }
        cursor = page.get("cursor")
        if not cursor:
            break
    return extra


def safe_float(s: Optional[str]) -> Optional[float]:
    if s is None or s == "":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_item(item: Dict[str, Any], prod_extra: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    cv_map = {cv["id"]: cv for cv in item.get("column_values", [])}

    def get_text(col_key: str) -> str:
        cv = cv_map.get(INSTALL_COL[col_key])
        return (cv.get("text") or "").strip() if cv else ""

    install_date = get_text("install_date")
    installer = get_text("installer")
    project_type = get_text("project_type")
    priority = get_text("priority")
    schedule_status = get_text("schedule_status")
    sales = get_text("sales")
    team = get_text("team")
    duration_raw = get_text("duration_hours")
    value_raw = get_text("installation_value")
    address = get_text("address")
    notes = get_text("notes")

    # production_link
    prod_link_cv = cv_map.get(INSTALL_COL["production_link"])
    prod_id: Optional[str] = None
    if prod_link_cv and prod_link_cv.get("value"):
        try:
            val = json.loads(prod_link_cv["value"])
            ids = val.get("linkedPulseIds") or []
            if ids:
                prod_id = str(ids[0].get("linkedPulseId"))
        except Exception:
            prod_id = None

    # Merge in extra production data
    extra = prod_extra.get(prod_id, {}) if prod_id else {}

    # Prefer Production project_type if Install Board doesn't have it
    if not project_type and extra.get("project_type"):
        project_type = extra["project_type"]

    return {
        "id": item["id"],
        "name": item["name"],
        "install_date": install_date,
        "address": address,
        "installer": installer,
        "schedule_status": schedule_status,
        "project_type": project_type,
        "priority": priority,
        "installation_value": safe_float(value_raw) or 0,
        "sales": sales,
        "notes": notes,
        "production_id": prod_id,
        "team": team,
        "duration_hours": safe_float(duration_raw) or safe_float(extra.get("plan_hours")),
        "invoice_number": extra.get("invoice_number", ""),
        "producer": extra.get("producer", ""),
        "plan_hours": extra.get("plan_hours", ""),
        "production_status": extra.get("status", ""),
    }


def main() -> None:
    items_raw = fetch_install_items()
    prod_extra = fetch_prod_extra()
    items = [parse_item(i, prod_extra) for i in items_raw]
    items.sort(key=lambda x: x["install_date"] or "9999-99-99")

    out = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(items),
        "items": items,
    }
    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log(f"已写 docs/data.json ({len(items)} 项)")


if __name__ == "__main__":
    main()
