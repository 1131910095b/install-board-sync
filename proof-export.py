"""
proof-export.py v5.2
从 Production Board 拉取 Sign Proof PDF（如果没有则从 Production File 拉），转换为 JPG。

v5.2 修改:
- 当 Sign Proof (file_mkth1r93) 为空时，从 Production File (file_mkthgv6d) 取
- 仍然优先 Sign Proof
- 支持多个 PDF（取第一个）
- 优先选 PDF，没 PDF 时也接受 JPG/PNG（直接复制）
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
import io

MONDAY_API_TOKEN = os.environ["MONDAY_API_TOKEN"]
PRODUCTION_BOARD_ID = "2053705854"
INSTALL_BOARD_ID = "5028736896"
PROOFS_DIR = Path("docs/proofs")
PROOFS_DIR.mkdir(parents=True, exist_ok=True)

SIGN_PROOF_COL = "file_mkth1r93"
PRODUCTION_FILE_COL = "file_mkthgv6d"

THUMBNAIL_WIDTH = 600
FULL_WIDTH = 1400
JPEG_QUALITY = 78


def log(msg):
    print(f"[{dt.datetime.now(dt.UTC).isoformat()}] {msg}", flush=True)


def monday_query(query):
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


def fetch_install_to_production_map():
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
                mapping[item["id"]] = str(cvs[0]["linked_item_ids"][0])
        cursor = page.get("cursor")
        if not cursor:
            break
    log(f"  {len(mapping)} 个映射")
    return mapping


def fetch_files(production_ids):
    """
    批量获取 Sign Proof + Production File 文件信息
    返回 {production_id: [{asset_id, name, url, size, ext, source}, ...]}
    优先 Sign Proof，没有时用 Production File
    """
    log(f"批量获取 {len(production_ids)} 个 Production 项目的文件...")
    result = {}
    # 注意：每批只查 10 个。文件列的 asset 嵌套查询复杂度高，
    # 一次查太多 (如 50) 会被 monday 截断响应、悄悄丢掉后面的项目，
    # 导致部分(常是较新的)项目抓不到 proof。
    CHUNK = 10
    for i in range(0, len(production_ids), CHUNK):
        chunk = production_ids[i:i+CHUNK]
        ids_str = ",".join(chunk)
        q = f"""
        query {{
          items(ids: [{ids_str}]) {{
            id
            signProof: column_values(ids: ["{SIGN_PROOF_COL}"]) {{
              ... on FileValue {{
                files {{
                  ... on FileAssetValue {{
                    asset_id
                    name
                    asset {{ file_extension file_size public_url }}
                  }}
                }}
              }}
            }}
            prodFile: column_values(ids: ["{PRODUCTION_FILE_COL}"]) {{
              ... on FileValue {{
                files {{
                  ... on FileAssetValue {{
                    asset_id
                    name
                    asset {{ file_extension file_size public_url }}
                  }}
                }}
              }}
            }}
          }}
        }}
        """
        data = monday_query(q)
        returned = data.get("items") or []
        if len(returned) < len(chunk):
            log(f"  ⚠ 警告：请求 {len(chunk)} 个项目，monday 只返回 {len(returned)} 个（可能被截断）")
        for item in returned:
            sign_files = (item.get("signProof") or [{}])[0].get("files") or []
            prod_files = (item.get("prodFile") or [{}])[0].get("files") or []
            
            chosen = []
            source = ""
            
            # Try Sign Proof first
            if sign_files:
                for f in sign_files:
                    a = f.get("asset", {})
                    ext = (a.get("file_extension") or "").lower().lstrip(".")
                    if ext in ("pdf", "jpg", "jpeg", "png"):
                        chosen.append({
                            "asset_id": f["asset_id"],
                            "name": f["name"],
                            "url": a["public_url"],
                            "size": a["file_size"],
                            "ext": ext,
                        })
                if chosen:
                    source = "sign_proof"
            
            # Fallback to Production File
            if not chosen and prod_files:
                for f in prod_files:
                    a = f.get("asset", {})
                    ext = (a.get("file_extension") or "").lower().lstrip(".")
                    if ext in ("pdf", "jpg", "jpeg", "png"):
                        chosen.append({
                            "asset_id": f["asset_id"],
                            "name": f["name"],
                            "url": a["public_url"],
                            "size": a["file_size"],
                            "ext": ext,
                        })
                if chosen:
                    source = "production_file"
            
            if chosen:
                # Tag each file with its source
                for c in chosen:
                    c["source"] = source
                result[item["id"]] = chosen
    
    by_source = {"sign_proof": 0, "production_file": 0}
    for prod_id, files in result.items():
        if files:
            by_source[files[0]["source"]] += 1
    log(f"  {len(result)} 个项目有文件 (Sign Proof: {by_source['sign_proof']}, Production File fallback: {by_source['production_file']})")
    return result


def download_file(url):
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content


def convert_pdf_to_images(pdf_bytes, prefix, max_pages=20, start_page=1):
    try:
        pages = convert_from_bytes(pdf_bytes, dpi=120, fmt="jpeg")
    except Exception as e:
        log(f"  ✗ PDF 解析失败: {e}")
        return []
    pages = pages[:max_pages]
    results = []
    for idx, page_img in enumerate(pages):
        i = start_page + idx
        # thumbnail
        thumb = page_img.copy()
        thumb.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 2))
        thumb_path = prefix.parent / f"{prefix.name}_p{i}_thumb.jpg"
        thumb.convert("RGB").save(thumb_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
        # full
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


def convert_image_to_jpgs(image_bytes, prefix, page=1):
    """Handle JPG/PNG: create _p{page}.jpg and _p{page}_thumb.jpg"""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception as e:
        log(f"  ✗ 图片解析失败: {e}")
        return []
    
    # thumb
    thumb = img.copy()
    thumb.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 2))
    thumb_path = prefix.parent / f"{prefix.name}_p{page}_thumb.jpg"
    thumb.convert("RGB").save(thumb_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
    # full
    full = img.copy()
    full.thumbnail((FULL_WIDTH, FULL_WIDTH * 2))
    full_path = prefix.parent / f"{prefix.name}_p{page}.jpg"
    full.convert("RGB").save(full_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return [{
        "page": page,
        "full": str(full_path.relative_to("docs")),
        "thumb": str(thumb_path.relative_to("docs")),
    }]


def get_cache_key(files):
    parts = [f"{a['asset_id']}:{a['size']}" for a in files]
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:12]


def main():
    log("=== 文件同步开始 ===")
    cache_file = Path("docs/proof_cache.json")
    cache = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text())
        except Exception:
            cache = {}

    install_to_prod = fetch_install_to_production_map()
    production_ids = list(set(install_to_prod.values()))
    files_by_prod = fetch_files(production_ids)

    proof_map = {}
    downloaded = 0
    skipped_cache = 0
    failed = 0
    current_keys = set()

    for prod_id, files in files_by_prod.items():
        cache_key = get_cache_key(files)
        current_keys.add(prod_id)

        if cache.get(prod_id, {}).get("key") == cache_key:
            cached_pages = cache[prod_id].get("pages", [])
            if cached_pages and all((Path("docs") / p["full"]).exists() for p in cached_pages):
                proof_map[prod_id] = cached_pages
                skipped_cache += 1
                continue

        try:
            prefix = PROOFS_DIR / prod_id
            pages = []
            next_page = 1
            for f in files:
                log(f"  下载 Production {prod_id}: {f['name']} [{f['source']}]")
                content = download_file(f["url"])
                if f["ext"] == "pdf":
                    new_pages = convert_pdf_to_images(content, prefix, start_page=next_page)
                else:
                    new_pages = convert_image_to_jpgs(content, prefix, page=next_page)
                pages.extend(new_pages)
                next_page += len(new_pages)
            
            if pages:
                proof_map[prod_id] = pages
                cache[prod_id] = {"key": cache_key, "pages": pages, "source": files[0]["source"]}
                downloaded += 1
                log(f"    ✓ {len(pages)} 页")
            else:
                failed += 1
        except Exception as e:
            failed += 1
            log(f"  ✗ Production {prod_id} 失败: {e}")

    # Clean obsolete
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

    cache_file.write_text(json.dumps(cache, indent=2))

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
    log(f"  docs/proofs.json: {len(install_proof_map)} 个 install 项目有文件")


if __name__ == "__main__":
    main()
