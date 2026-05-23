"""
从 Production Board 拉取 Sign Proof PDF，转换为 JPG，保存到 docs/proofs/

依赖：requests, pdf2image, Pillow
系统依赖：poppler-utils (apt install poppler-utils)
"""
import os
import json
import hashlib
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from pdf2image import convert_from_bytes
from PIL import Image

MONDAY_API_TOKEN = os.environ["MONDAY_API_TOKEN"]
PRODUCTION_BOARD_ID = "2053705854"
INSTALL_BOARD_ID = "5028736896"
PROOFS_DIR = Path("docs/proofs")
PROOFS_DIR.mkdir(parents=True, exist_ok=True)

# 图片输出设置
THUMBNAIL_WIDTH = 600   # 列表卡片用的缩略图宽度
FULL_WIDTH = 1400       # 详情页/PDF 用的大图宽度
JPEG_QUALITY = 75


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.UTC).isoformat()}] {msg}", flush=True)


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
        raise RuntimeError(f"GraphQL: {data['errors']}")
    return data["data"]


def fetch_install_to_production_map() -> Dict[str, str]:
    """从 Install Board 拉对应 Production Item ID"""
    log("读取 Install Board → Production 映射...")
    mapping = {}
    cursor = None
    while True:
        cur = f', cursor: "{cursor}"' if cursor else ""
        q = f"""
        query {{
          boards(ids: [{INSTALL_BOARD_ID}]) {{
            items_page(limit: 500{cur}) {{
              cursor
              items {{
                id
                column_values(ids: ["board_relation_mm3mj5j8"]) {{
                  ... on BoardRelationValue {{
                    linked_item_ids
                  }}
                }}
              }}
            }}
          }}
        }}
        """
        data = monday_query(q)
        page = data["boards"][0]["items_page"]
        for item in page["items"]:
            cvs = item.get("column_values", [])
            if cvs and cvs[0].get("linked_item_ids"):
                # install_item_id → production_item_id
                mapping[item["id"]] = str(cvs[0]["linked_item_ids"][0])
        cursor = page.get("cursor")
        if not cursor:
            break
    log(f"  {len(mapping)} 个映射")
    return mapping


def fetch_sign_proofs(production_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """批量拉 Sign Proof 文件信息，返回 {production_id: [{asset_id, public_url, file_size}, ...]}"""
    log(f"批量获取 {len(production_ids)} 个 Production 项目的 Sign Proof...")
    result = {}
    # 分批查询（一次最多 100 个）
    for i in range(0, len(production_ids), 50):
        chunk = production_ids[i:i+50]
        ids_str = ",".join(chunk)
        q = f"""
        query {{
          items(ids: [{ids_str}]) {{
            id
            column_values(ids: ["file_mkth1r93"]) {{
              ... on FileValue {{
                files {{
                  ... on FileAssetValue {{
                    asset_id
                    name
                    asset {{
                      file_extension
                      file_size
                      public_url
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
        """
        data = monday_query(q)
        for item in data["items"]:
            cvs = item.get("column_values", [])
            if not cvs or not cvs[0].get("files"):
                continue
            files = cvs[0]["files"]
            pdfs = []
            for f in files:
                if f.get("asset", {}).get("file_extension", "").lower() in [".pdf", "pdf"]:
                    pdfs.append({
                        "asset_id": f["asset_id"],
                        "name": f["name"],
                        "url": f["asset"]["public_url"],
                        "size": f["asset"]["file_size"],
                    })
            if pdfs:
                result[item["id"]] = pdfs
    log(f"  {len(result)} 个项目有 Sign Proof PDF")
    return result


def download_pdf(url: str) -> bytes:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content


def convert_pdf_to_images(pdf_bytes: bytes, prefix: Path, max_pages: int = 20) -> List[Dict[str, str]]:
    """
    PDF 转 JPG，每页两张：
    - {prefix}_p{n}.jpg (full size)
    - {prefix}_p{n}_thumb.jpg (thumbnail)
    返回 [{page, full, thumb}, ...]
    """
    try:
        pages = convert_from_bytes(pdf_bytes, dpi=120, fmt="jpeg")
    except Exception as e:
        log(f"  ✗ PDF 解析失败: {e}")
        return []

    pages = pages[:max_pages]
    results = []
    for i, page_img in enumerate(pages, 1):
        # 缩略图
        thumb = page_img.copy()
        thumb.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 2))
        thumb_path = prefix.parent / f"{prefix.name}_p{i}_thumb.jpg"
        thumb.convert("RGB").save(thumb_path, "JPEG", quality=JPEG_QUALITY, optimize=True)

        # 大图
        full = page_img.copy()
        full.thumbnail((FULL_WIDTH, FULL_WIDTH * 2))
        full_path = prefix.parent / f"{prefix.name}_p{i}.jpg"
        full.convert("RGB").save(full_path, "JPEG", quality=JPEG_QUALITY, optimize=True)

        results.append({
            "page": i,
            "full": str(full_path.relative_to("docs")),
            "thumb": str(thumb_path.relative_to("docs")),
        })
    return results


def get_proof_cache_key(asset_info: List[Dict]) -> str:
    """根据 asset_id + size 算 hash，判断是否需要重新下载"""
    parts = [f"{a['asset_id']}:{a['size']}" for a in asset_info]
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:12]


def main() -> None:
    log("=== Sign Proof 同步开始 ===")

    # 加载缓存（记录每个 production_id 上次的 hash，避免重复下载）
    cache_file = Path("docs/proof_cache.json")
    cache = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text())
        except Exception:
            cache = {}

    # 1. install → production 映射
    install_to_prod = fetch_install_to_production_map()
    production_ids = list(set(install_to_prod.values()))

    # 2. 批量拉 Sign Proof 文件信息
    proofs_by_prod = fetch_sign_proofs(production_ids)

    # 3. 下载新的 + 删除过期的
    proof_map: Dict[str, List[Dict[str, Any]]] = {}  # production_id → pages info
    downloaded = 0
    skipped_cache = 0
    failed = 0

    current_keys = set()  # 本次有 proof 的 production_id 列表

    for prod_id, assets in proofs_by_prod.items():
        cache_key = get_proof_cache_key(assets)
        current_keys.add(prod_id)

        # 缓存命中：用旧的
        if cache.get(prod_id, {}).get("key") == cache_key:
            cached_pages = cache[prod_id].get("pages", [])
            # 验证文件还在
            if cached_pages and all((Path("docs") / p["full"]).exists() for p in cached_pages):
                proof_map[prod_id] = cached_pages
                skipped_cache += 1
                continue

        # 缓存未命中：下载第一个 PDF
        try:
            log(f"  下载 Production {prod_id}: {assets[0]['name']}")
            pdf_bytes = download_pdf(assets[0]["url"])
            prefix = PROOFS_DIR / prod_id
            pages = convert_pdf_to_images(pdf_bytes, prefix)
            if pages:
                proof_map[prod_id] = pages
                cache[prod_id] = {"key": cache_key, "pages": pages}
                downloaded += 1
                log(f"    ✓ {len(pages)} 页")
            else:
                failed += 1
        except Exception as e:
            failed += 1
            log(f"  ✗ Production {prod_id} 失败: {e}")

    # 4. 清理：删除已经不在 production 上的 proof 文件
    cleaned = 0
    obsolete = set(cache.keys()) - current_keys
    for prod_id in obsolete:
        for p in cache[prod_id].get("pages", []):
            for path_key in ("full", "thumb"):
                f = Path("docs") / p.get(path_key, "")
                if f.exists():
                    try:
                        f.unlink()
                        cleaned += 1
                    except Exception:
                        pass
        cache.pop(prod_id, None)

    # 5. 保存缓存
    cache_file.write_text(json.dumps(cache, indent=2))

    # 6. 把 production_id → install_id 反向写到 data.json 的补充文件
    install_proof_map = {}
    for install_id, prod_id in install_to_prod.items():
        if prod_id in proof_map:
            install_proof_map[install_id] = proof_map[prod_id]

    Path("docs/proofs.json").write_text(
        json.dumps({
            "generated_at": dt.datetime.now(dt.UTC).isoformat() + "Z",
            "proofs": install_proof_map,
        }, indent=2)
    )

    log(f"=== 完成 ===")
    log(f"  下载: {downloaded}, 缓存命中: {skipped_cache}, 失败: {failed}, 清理过期: {cleaned}")
    log(f"  docs/proofs.json: {len(install_proof_map)} 个 install 项目有 proof")


if __name__ == "__main__":
    main()
