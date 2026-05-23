"""
Install Board → data.json 导出脚本

每次跑会把 Install Board 全部项目导出为 docs/data.json，
网页可以静态读取（不需要 monday token 暴露在前端）。
"""
import os
import json
import datetime as dt
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
}


def monday_query(query: str) -> Dict[str, Any]:
    r = requests.post(
        "https://api.monday.com/v2",
        headers={
            "Authorization": MONDAY_API_TOKEN,
            "Content-Type": "application/json",
            "API-Version": "2024-01",
        },
        json={"query": query},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]


def fetch_all_items() -> List[Dict[str, Any]]:
    col_ids = list(COL.values())
    col_ids_json = json.dumps(col_ids)

    items = []
    cursor = None
    while True:
        cursor_part = f', cursor: "{cursor}"' if cursor else ""
        query = f"""
        query {{
          boards(ids: [{INSTALL_BOARD_ID}]) {{
            items_page(limit: 500{cursor_part}) {{
              cursor
              items {{
                id
                name
                column_values(ids: {col_ids_json}) {{
                  id
                  text
                  value
                }}
              }}
            }}
          }}
        }}
        """
        data = monday_query(query)
        page = data["boards"][0]["items_page"]
        for item in page["items"]:
            vals = {cv["id"]: {"text": cv.get("text"), "value": cv.get("value")}
                    for cv in item.get("column_values", [])}
            items.append({
                "id": item["id"],
                "name": item["name"],
                "install_date": vals.get(COL["install_date"], {}).get("text") or "",
                "address": vals.get(COL["address"], {}).get("text") or "",
                "installer": vals.get(COL["installer"], {}).get("text") or "",
                "schedule_status": vals.get(COL["schedule_status"], {}).get("text") or "",
                "project_type": vals.get(COL["project_type"], {}).get("text") or "",
                "priority": vals.get(COL["priority"], {}).get("text") or "",
                "installation_value": vals.get(COL["installation_value"], {}).get("text") or "",
                "sales": vals.get(COL["sales"], {}).get("text") or "",
                "notes": vals.get(COL["notes"], {}).get("text") or "",
            })
        cursor = page.get("cursor")
        if not cursor:
            break
    return items


def main() -> None:
    print(f"[{dt.datetime.utcnow().isoformat()}] 导出 Install Board 数据...")
    items = fetch_all_items()
    print(f"  共 {len(items)} 个项目")

    # 按 install_date 过滤 + 排序，只保留今天前30天到未来 60 天的
    today = dt.date.today()
    cutoff_past = today - dt.timedelta(days=30)
    cutoff_future = today + dt.timedelta(days=60)

    filtered = []
    for item in items:
        if not item["install_date"]:
            continue
        try:
            d = dt.datetime.strptime(item["install_date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if cutoff_past <= d <= cutoff_future:
            filtered.append(item)

    filtered.sort(key=lambda x: x["install_date"])

    output = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "count": len(filtered),
        "items": filtered,
    }

    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  写入 docs/data.json: {len(filtered)} 个项目")


if __name__ == "__main__":
    main()
