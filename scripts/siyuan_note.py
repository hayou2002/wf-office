#!/usr/bin/env python3
"""Read, create, append, and verify SiYuan notes without exposing the API token."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
REMOTE_RE = re.compile(r"^(?:https?:|data:|#)")


class SiYuanError(RuntimeError):
    pass


def home() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home())


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SiYuanError(f"读不了配置文件 {path.name}: {exc}") from exc


def load_config() -> tuple[str, str | None]:
    port = os.environ.get("SIYUAN_PORT")
    if not port:
        port_file = home() / ".config" / "siyuan" / "port.json"
        ports = read_json(port_file)
        if not isinstance(ports, dict) or not ports:
            raise SiYuanError("port.json 里没有端口")
        port = str(next(iter(ports.values())))
    token = os.environ.get("SIYUAN_TOKEN")
    if not token:
        workspace = os.environ.get("SIYUAN_WORKSPACE")
        if not workspace:
            workspace_file = home() / ".config" / "siyuan" / "workspace.json"
            workspaces = read_json(workspace_file)
            if not isinstance(workspaces, list) or not workspaces:
                raise SiYuanError("workspace.json 里没有工作区")
            workspace = workspaces[0]
        conf_file = Path(workspace) / "conf" / "conf.json"
        conf = read_json(conf_file)
        token = conf.get("accessAuthCode") or None
    return port, token


def base_url() -> str:
    port, _ = load_config()
    return f"http://127.0.0.1:{port}"


def headers(content_type: str | None = None) -> dict[str, str]:
    _, token = load_config()
    result = {"Accept": "application/json"}
    if token:
        result["Authorization"] = f"Token {token}"
    if content_type:
        result["Content-Type"] = content_type
    return result


def request_json(path: str, payload: dict | None = None) -> dict:
    url = base_url() + path
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=body, headers=headers("application/json"), method="POST")
    try:
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise SiYuanError(f"{path} 返回 HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise SiYuanError(f"连不上思源 {url}: {exc.reason}") from exc


def post_api(path: str, payload: dict | None = None) -> dict:
    data = request_json(path, payload)
    if data.get("code") != 0:
        raise SiYuanError(f"{path} 失败：{data.get('msg') or data}")
    return data


def sql_quote(value: str) -> str:
    return value.replace("'", "''")


def query(stmt: str) -> list[dict]:
    data = post_api("/api/query/sql", {"stmt": stmt})
    rows = data.get("data")
    return rows if isinstance(rows, list) else []


def all_docs(limit: int = 2000) -> list[dict]:
    return query(
        "select id,content,hpath,box,updated from blocks "
        f"where type='d' order by updated desc limit {limit}"
    )


def notebook_list() -> list[dict]:
    data = post_api("/api/notebook/lsNotebooks")
    return (data.get("data") or {}).get("notebooks") or []


def get_doc(doc_id: str) -> dict:
    rows = query(
        "select id,content,hpath,box,updated from blocks "
        f"where type='d' and id='{sql_quote(doc_id)}' limit 1"
    )
    if not rows:
        raise SiYuanError(f"找不到文档 {doc_id}")
    return rows[0]


def children_of(doc: dict) -> list[dict]:
    prefix = str(doc.get("hpath", "")).rstrip("/") + "/"
    depth = prefix.count("/")
    rows = [row for row in all_docs() if row.get("hpath", "").startswith(prefix)]
    return [row for row in rows if row.get("hpath", "").count("/") == depth]


def block_counts(doc_id: str) -> dict[str, int]:
    rows = query(
        "select type,count(*) as n from blocks "
        f"where root_id='{sql_quote(doc_id)}' group by type"
    )
    return {str(row.get("type")): int(row.get("n") or 0) for row in rows}


def image_count(doc_id: str) -> int:
    rows = query(
        "select count(*) as n from blocks "
        f"where root_id='{sql_quote(doc_id)}' and content like '%assets/%'"
    )
    return int(rows[0].get("n") or 0) if rows else 0


def edge_content(doc_id: str, direction: str) -> str:
    order = "desc" if direction == "last" else "asc"
    rows = query(
        "select content from blocks "
        f"where root_id='{sql_quote(doc_id)}' and type='p' and content <> '' "
        f"order by sort {order}, id {order} limit 1"
    )
    return str(rows[0].get("content") or "") if rows else ""


def emit(value: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    for key, item in value.items():
        if isinstance(item, dict):
            print(f"{key}:")
            for sub_key, sub_item in item.items():
                print(f"  {sub_key}: {sub_item}")
        elif isinstance(item, list):
            print(f"{key}:")
            for entry in item:
                print(f"  {entry}")
        else:
            print(f"{key}: {item}")


def resolve_title(term: str, notebook: str | None = None) -> list[dict]:
    docs = all_docs()
    if notebook:
        notebooks = notebook_list()
        matched = [item for item in notebooks if notebook in (item.get("id"), item.get("name"))]
        if not matched:
            raise SiYuanError(f"找不到笔记本 {notebook}")
        box = matched[0]["id"]
        docs = [row for row in docs if row.get("box") == box]
    lowered = term.casefold()
    docs = [row for row in docs if lowered in str(row.get("content", "")).casefold()]
    exact = [row for row in docs if str(row.get("content", "")) == term]
    result = exact or docs
    return [
        {
            "id": row.get("id"),
            "title": row.get("content"),
            "hpath": row.get("hpath"),
            "updated": row.get("updated"),
        }
        for row in result
    ]


def cmd_resolve(args) -> int:
    result = resolve_title(args.title, args.notebook)
    emit({"matches": result, "count": len(result)}, args.json)
    return 0 if result else 2


def cmd_inspect(args) -> int:
    doc = get_doc(args.doc)
    children = children_of(doc)
    emit(
        {
            "doc": {
                "id": doc.get("id"),
                "title": doc.get("content"),
                "hpath": doc.get("hpath"),
                "notebook": doc.get("box"),
                "updated": doc.get("updated"),
            },
            "is_parent": bool(children),
            "children": [
                {"id": row.get("id"), "title": row.get("content"), "hpath": row.get("hpath")}
                for row in children
            ],
            "counts": block_counts(str(doc.get("id"))),
            "images": image_count(str(doc.get("id"))),
        },
        args.json,
    )
    return 0


def markdown_images(text: str) -> list[tuple[str, str]]:
    return [(match.group(1), match.group(2).strip()) for match in IMAGE_RE.finditer(text)]


def local_asset_path(target: str, md_path: Path, assets_dir: str | None) -> Path:
    clean = target.split(" ")[0].strip("<>").split("?")[0].split("#")[0]
    candidate = (md_path.parent / clean).resolve()
    if candidate.exists():
        return candidate
    if assets_dir:
        candidate = (Path(assets_dir) / Path(clean).name).resolve()
        if candidate.exists():
            return candidate
    raise SiYuanError(f"图片不存在：{target}")


def multipart_body(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    boundary = "----wfdesign" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    data = file_path.read_bytes()
    chunks.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file[]"; '
            f'filename="{file_path.name}"\r\nContent-Type: {mime}\r\n\r\n'
        ).encode("utf-8")
    )
    chunks.append(data)
    chunks.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def upload_asset(file_path: Path) -> str:
    body, content_type = multipart_body({"assetsDirPath": "/assets/"}, file_path)
    req = Request(
        base_url() + "/api/asset/upload",
        data=body,
        headers={**headers(content_type), "Content-Type": content_type},
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise SiYuanError(f"上传 {file_path.name} 返回 HTTP {exc.code}") from exc
    except URLError as exc:
        raise SiYuanError(f"上传 {file_path.name} 时连不上思源：{exc.reason}") from exc
    if data.get("code") != 0:
        raise SiYuanError(f"上传 {file_path.name} 失败：{data.get('msg') or data}")
    payload = data.get("data") or {}
    if payload.get("errFiles"):
        raise SiYuanError(f"上传 {file_path.name} 失败：{payload['errFiles']}")
    succ_map = payload.get("succMap") or {}
    if not succ_map:
        raise SiYuanError(f"上传 {file_path.name} 没有返回资源路径")
    path = str(next(iter(succ_map.values()))).lstrip("/")
    return path


def prepare_markdown(md_path: Path, assets_dir: str | None, dry_run: bool) -> tuple[str, list[dict]]:
    try:
        text = md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SiYuanError(f"读不了 Markdown {md_path}: {exc}") from exc
    images: list[dict] = []
    for alt, target in markdown_images(text):
        clean = target.split(" ")[0].strip("<>")
        if REMOTE_RE.match(clean):
            images.append({"target": clean, "status": "remote"})
            continue
        asset = local_asset_path(clean, md_path, assets_dir)
        if dry_run:
            images.append({"target": clean, "status": "ready", "file": str(asset)})
            continue
        uploaded = upload_asset(asset)
        text = text.replace(f"]({target})", f"]({uploaded})")
        images.append({"target": clean, "status": "uploaded", "path": uploaded})
    return text, images


def do_create(args) -> tuple[str, str, dict, str]:
    parent = get_doc(args.parent)
    notebook = str(parent.get("box"))
    parent_hpath = str(parent.get("hpath") or "").rstrip("/")
    target_hpath = f"{parent_hpath}/{args.title.strip('/')}"
    existing = [row for row in all_docs() if row.get("hpath") == target_hpath]
    if existing:
        if args.on_duplicate == "error":
            raise SiYuanError(f"已存在同名文档：{existing[0].get('id')}")
        doc = existing[0]
        return "append", str(doc.get("id")), {"doc": doc, "hpath": target_hpath}, notebook
    return "create", "", {"parent": parent, "hpath": target_hpath}, notebook


def cmd_create(args) -> int:
    mode, doc_id, info, notebook = do_create(args)
    text, images = prepare_markdown(Path(args.file), args.assets, args.dry_run)
    result = {
        "mode": mode,
        "dry_run": bool(args.dry_run),
        "notebook": notebook,
        "hpath": info["hpath"],
        "chars": len(text),
        "images": images,
    }
    if doc_id:
        result["doc"] = doc_id
    if args.dry_run:
        emit(result, args.json)
        return 0
    if mode == "append":
        before_total = sum(block_counts(doc_id).values())
        data = post_api(
            "/api/block/appendBlock",
            {"dataType": "markdown", "data": text, "parentID": doc_id},
        )
        result["doc"] = doc_id
    else:
        data = post_api(
            "/api/filetree/createDocWithMd",
            {"notebook": notebook, "path": info["hpath"], "markdown": text},
        )
        payload = data.get("data")
        if isinstance(payload, dict):
            doc_id = str(payload.get("id") or "")
        else:
            doc_id = str(payload or "")
        if not doc_id:
            raise SiYuanError("新建成功但没有返回文档 ID")
        result["doc"] = doc_id
    time.sleep(1.0)
    min_total = before_total + 1 if mode == "append" else None
    result["verify"] = verify_with_retry(doc_id, min_total=min_total)
    emit(result, args.json)
    return 0


def cmd_append(args) -> int:
    doc = get_doc(args.doc)
    text, images = prepare_markdown(Path(args.file), args.assets, args.dry_run)
    result = {
        "mode": "append",
        "dry_run": bool(args.dry_run),
        "doc": args.doc,
        "title": doc.get("content"),
        "hpath": doc.get("hpath"),
        "chars": len(text),
        "images": images,
    }
    if args.dry_run:
        emit(result, args.json)
        return 0
    before_total = sum(block_counts(args.doc).values())
    post_api("/api/block/appendBlock", {"dataType": "markdown", "data": text, "parentID": args.doc})
    time.sleep(1.0)
    result["verify"] = verify_with_retry(args.doc, min_total=before_total + 1)
    emit(result, args.json)
    return 0


def verify_doc(doc_id: str) -> dict:
    try:
        doc = get_doc(doc_id)
    except SiYuanError as exc:
        return {"ok": False, "error": str(exc)}
    counts = block_counts(doc_id)
    images = image_count(doc_id)
    result = {
        "ok": counts.get("h", 0) > 0 and counts.get("p", 0) > 0,
        "doc": doc_id,
        "title": doc.get("content"),
        "hpath": doc.get("hpath"),
        "counts": counts,
        "headings": counts.get("h", 0),
        "tables": counts.get("t", 0),
        "code_blocks": counts.get("c", 0),
        "images": images,
        "first": edge_content(doc_id, "first")[:160],
        "last": edge_content(doc_id, "last")[:160],
    }
    return result


def verify_with_retry(doc_id: str, attempts: int = 8, min_total: int | None = None) -> dict:
    result = verify_doc(doc_id)
    for _ in range(attempts - 1):
        total = sum(result.get("counts", {}).values())
        if result.get("ok") and (min_total is None or total >= min_total):
            return result
        time.sleep(0.5)
        result = verify_doc(doc_id)
    return result


def cmd_verify(args) -> int:
    result = verify_doc(args.doc)
    emit(result, args.json)
    return 0 if result.get("ok") else 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="siyuan_note.py", description="思源知识笔记读写助手")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve", help="按标题查文档")
    resolve.add_argument("--title", required=True)
    resolve.add_argument("--notebook", help="笔记本名称或 ID")
    resolve.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    resolve.set_defaults(func=cmd_resolve)

    inspect = sub.add_parser("inspect", help="查看文档和子文档")
    inspect.add_argument("--doc", required=True)
    inspect.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    inspect.set_defaults(func=cmd_inspect)

    create = sub.add_parser("create", help="在父文档下新建子文档")
    create.add_argument("--parent", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--file", required=True)
    create.add_argument("--assets", help="图片目录，默认按 Markdown 相对路径找")
    create.add_argument("--dry-run", action="store_true")
    create.add_argument("--on-duplicate", choices=("append", "error"), default="append")
    create.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    create.set_defaults(func=cmd_create)

    append = sub.add_parser("append", help="追加 Markdown 到已有文档")
    append.add_argument("--doc", required=True)
    append.add_argument("--file", required=True)
    append.add_argument("--assets", help="图片目录，默认按 Markdown 相对路径找")
    append.add_argument("--dry-run", action="store_true")
    append.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    append.set_defaults(func=cmd_append)

    verify = sub.add_parser("verify", help="回读文档")
    verify.add_argument("--doc", required=True)
    verify.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    verify.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.json = bool(getattr(args, "json", False))
    try:
        return args.func(args)
    except SiYuanError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
