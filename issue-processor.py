"""
issue-processor.py
读取 GitHub Issues 中的"date change"请求，把新的 install_date 写回 monday Production Board，
然后关闭 issue。

Issue 的 title 格式: [DATE-CHANGE] <prod_id> <new_date>
例如: [DATE-CHANGE] 2595267924 2026-05-30
"""
import json
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

MONDAY_API_TOKEN = os.environ["MONDAY_API_TOKEN"]
GITHUB_TOKEN = os.environ["GH_TOKEN"]
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "1131910095b/install-board-sync")

PROD_BOARD_ID = "2053705854"
PROD_INSTALL_DATE_COL = "date_mm1dqz30"


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


def gh_request(method: str, url: str, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", {})
    headers.update({
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return requests.request(method, url, headers=headers, timeout=30, **kwargs)


def fetch_open_issues() -> List[Dict[str, Any]]:
    log("读取 GitHub Issues...")
    issues: List[Dict[str, Any]] = []
    page = 1
    while True:
        r = gh_request(
            "GET",
            f"https://api.github.com/repos/{GITHUB_REPO}/issues",
            params={"state": "open", "per_page": 100, "page": page},
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        issues.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    log(f"共 {len(issues)} 个开放的 issues")
    return issues


def close_issue(issue_number: int, comment: str = "") -> None:
    if comment:
        gh_request(
            "POST",
            f"https://api.github.com/repos/{GITHUB_REPO}/issues/{issue_number}/comments",
            json={"body": comment},
        )
    gh_request(
        "PATCH",
        f"https://api.github.com/repos/{GITHUB_REPO}/issues/{issue_number}",
        json={"state": "closed"},
    )


def update_install_date(prod_id: str, new_date: str) -> None:
    monday_query(
        """
        mutation ($board: ID!, $item: ID!, $col: String!, $val: JSON!) {
          change_column_value(board_id: $board, item_id: $item, column_id: $col, value: $val) { id }
        }""",
        {
            "board": PROD_BOARD_ID,
            "item": prod_id,
            "col": PROD_INSTALL_DATE_COL,
            "val": json.dumps({"date": new_date}),
        },
    )


def main() -> None:
    log("开始处理 GitHub Issues")
    issues = fetch_open_issues()
    processed = 0
    failed = 0

    title_re = re.compile(r"^\[DATE-CHANGE\]\s+(\d+)\s+(\d{4}-\d{2}-\d{2})\s*$")

    for issue in issues:
        title = issue.get("title", "").strip()
        m = title_re.match(title)
        if not m:
            continue
        prod_id, new_date = m.group(1), m.group(2)
        try:
            update_install_date(prod_id, new_date)
            close_issue(issue["number"], f"✓ Production item {prod_id} install_date updated to {new_date}")
            log(f"  ✓ #{issue['number']}: {prod_id} → {new_date}")
            processed += 1
        except Exception as e:
            failed += 1
            log(f"  ✗ #{issue['number']} 失败: {e}")
            try:
                gh_request(
                    "POST",
                    f"https://api.github.com/repos/{GITHUB_REPO}/issues/{issue['number']}/comments",
                    json={"body": f"⚠️ Failed to update: {e}"},
                )
            except Exception:
                pass

    log(f"完成 ✓ 处理 {processed}，失败 {failed}")


if __name__ == "__main__":
    main()
