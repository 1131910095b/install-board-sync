"""
Install Board → docs/data.json
v4: 增加 team + duration_hours 字段，供 Outlook 风格周视图使用
"""
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

MONDAY_API_TOKEN = os.environ["MONDAY_API_TOKEN"]
INSTALL_BOARD_ID = "5028736896"

COL = {
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


def fetch_all_items() -> List[Dict[str, Any]]:
    log("读取 Install Board 所有项目...")
    all_items: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    column_ids_str = json.dumps(list(COL.values()))
    while True:
        if cursor:
            query = f"""
            query ($board: ID!, $cursor: String!) {{
              boards(ids: [$board]) {{
                items_page(limit: 200, cursor: $cursor) {{
                  cursor
                  items {{
                    id
                    name
                    column_values(ids: {column_ids_str}) {{ id text value }}
                  }}
                }}
              }}
            }}"""
            vars_ = {"board": INSTALL_BOARD_ID, "cursor": cursor}
        else:
            query = f"""
            query ($board: ID!) {{
              boards(ids: [$board]) {{
                items_page(limit: 200) {{
                  cursor
                  items {{
                    id
                    name
                    column_values(ids: {column_ids_str}) {{ id text value }}
                  }}
                }}
              }}
            }}"""
            vars_ = {"board": INSTALL_BOARD_ID}
        data = monday_query(query, vars_)
        page = data["boards"][0]["items_page"]
        all_items.extend(page["items"])
        cursor = page.get("cursor")
        if not cursor:
            break
    log(f"读取 {len(all_items)} 个项目")
    return all_items


def safe_float(s: Optional[str]) -> Optional[float]:
    if s is None or s == "":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_item(item: Dict[str, Any]) -> Dict[str, Any]:
    cv_map: Dict[str, Dict[str, Any]] = {cv["id"]: cv for cv in item.get("column_values", [])}

    def get_text(col_key: str) -> str:
        cv = cv_map.get(COL[col_key])
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

    # production_link 拿 item id
    prod_link_cv = cv_map.get(COL["production_link"])
    prod_id: Optional[str] = None
    if prod_link_cv and prod_link_cv.get("value"):
        try:
            val = json.loads(prod_link_cv["value"])
            ids = val.get("linkedPulseIds") or []
            if ids:
                prod_id = str(ids[0].get("linkedPulseId"))
        except Exception:
            prod_id = None

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
        "duration_hours": safe_float(duration_raw),
    }


def main() -> None:
    items_raw = fetch_all_items()
    items = [parse_item(i) for i in items_raw]
    # 按日期排序
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
