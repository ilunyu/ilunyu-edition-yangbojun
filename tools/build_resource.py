#!/usr/bin/env python3
"""Build the Yang Bojun edition as an Android .ilunyupack resource."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PIAN_FILE = re.compile(r"^(\d{2})-[a-z0-9-]+\.json$")
MARKER = re.compile(r"\[(\d+)\]")
PACKAGE_FORMAT = 1
CONTENT_SCHEMA = 1


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: root must be an object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def chapter_stub(chapter: dict[str, Any]) -> dict[str, Any]:
    return {key: chapter[key] for key in ("id", "number", "displayId")}


def chapter_preview(chapter: dict[str, Any]) -> dict[str, Any]:
    return {
        **chapter_stub(chapter),
        "plainText": chapter["plainText"],
        "translation": chapter["translation"],
        "annotations": [],
    }


def build_edition() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    metadata = read_json(ROOT / "metadata.json")
    pian_paths = sorted(path for path in ROOT.glob("*.json") if PIAN_FILE.match(path.name))
    if len(pian_paths) != 20:
        raise ValueError(f"expected 20 pian files, found {len(pian_paths)}")

    pians: list[dict[str, Any]] = []
    ids: set[str] = set()
    for pian_number, pian_path in enumerate(pian_paths, start=1):
        match = PIAN_FILE.match(pian_path.name)
        assert match is not None
        if int(match.group(1)) != pian_number:
            raise ValueError(f"{pian_path.name}: pian sequence is invalid")
        raw = read_json(pian_path)
        title = raw.get("title")
        content = raw.get("content")
        if not isinstance(title, str) or not title.strip() or not isinstance(content, list) or not content:
            raise ValueError(f"{pian_path.name}: title and content are required")
        chapters: list[dict[str, Any]] = []
        for number, item in enumerate(content, start=1):
            if not isinstance(item, dict) or item.get("id") is None:
                raise ValueError(f"{pian_path.name}: chapter {number} has no id")
            chapter_id = str(item["id"])
            if chapter_id in ids:
                raise ValueError(f"duplicate chapter id: {chapter_id}")
            ids.add(chapter_id)
            annotations = []
            for index, note in enumerate(item.get("annotation", []), start=1):
                if not isinstance(note, dict):
                    raise ValueError(f"{pian_path.name}: annotation {index} is invalid")
                annotations.append({
                    "index": index,
                    "label": str(note.get("label", "")),
                    "text": str(note.get("text", note.get("content", ""))),
                })
            text = str(item.get("text", ""))
            chapters.append({
                "id": chapter_id,
                "number": number,
                "displayId": f"{pian_number}·{number}",
                "text": text,
                "plainText": MARKER.sub("", text),
                "translation": str(item.get("translate", "")),
                "annotations": annotations,
                "comment": str(item.get("comment", "")),
                "sourceReference": str(item.get("sourceReference", "")),
            })
        pians.append({
            "id": f"{pian_number:02d}",
            "number": pian_number,
            "slug": pian_path.stem,
            "title": title,
            "shortTitle": re.sub(r"篇第.+$", "", title),
            "comment": str(raw.get("comment", "")),
            "chapterCount": len(chapters),
            "chapters": chapters,
        })

    book_name = str(metadata.get("book_name", "论语译注"))
    author = str(metadata.get("book_author", ""))
    short_name = str(metadata.get("short_name", "")).strip()
    if not short_name:
        short_name = f"{author}《{book_name.split('（', 1)[0]}》" if author else book_name
    source = {
        "id": ROOT.name,
        "name": book_name,
        "shortName": short_name,
        "author": author,
        "publisher": str(metadata.get("book_publisher", "")),
        "description": str(metadata.get("description", "")),
    }
    stats = {"pianCount": len(pians), "chapterCount": sum(pian["chapterCount"] for pian in pians)}
    catalog = {
        "formatVersion": 2,
        "source": source,
        "stats": stats,
        "pians": [{
            **{key: pian[key] for key in ("id", "number", "slug", "title", "shortTitle", "chapterCount")},
            "chapters": [chapter_stub(chapter) for chapter in pian["chapters"]],
        } for pian in pians],
    }
    search = {
        "formatVersion": 2,
        "source": source,
        "stats": stats,
        "pians": [{
            **{key: pian[key] for key in ("id", "number", "slug", "title", "shortTitle", "comment", "chapterCount")},
            "chapters": [chapter_preview(chapter) for chapter in pian["chapters"]],
        } for pian in pians],
    }
    return catalog, search, pians


def write_package(output: Path) -> dict[str, Any]:
    config = read_json(ROOT / "resource.json")
    catalog, search, pians = build_edition()
    with tempfile.TemporaryDirectory(prefix="ilunyu-package-") as directory:
        build = Path(directory)
        content = build / "content"
        write_json(content / "catalog.json", catalog)
        write_json(content / "search.json", search)
        for pian in pians:
            pian_payload = {
                **{key: pian[key] for key in ("id", "number", "slug", "title", "shortTitle", "comment", "chapterCount")},
                "chapters": [chapter_preview(chapter) for chapter in pian["chapters"]],
            }
            write_json(content / "pian" / f"{pian['slug']}.json", pian_payload)
            for chapter in pian["chapters"]:
                write_json(content / "chapters" / f"{chapter['id']}.json", chapter)
        file_hashes = {
            path.relative_to(build).as_posix(): f"sha256:{sha256(path)}"
            for path in sorted(content.rglob("*.json"))
        }
        manifest = {
            "packageFormat": PACKAGE_FORMAT,
            "contentSchema": CONTENT_SCHEMA,
            "packageId": config["packageId"],
            "kind": config["kind"],
            "name": catalog["source"]["shortName"],
            "versionName": config["versionName"],
            "versionCode": config["versionCode"],
            "minAppVersionCode": config["minAppVersionCode"],
            "sourceRepository": config.get("sourceRepository", "https://github.com/ilunyu/ilunyu-edition-yangbojun"),
            "license": config.get("license", ""),
            "createdAt": config.get("createdAt", ""),
            "files": file_hashes,
        }
        write_json(build / "manifest.json", manifest)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(build.rglob("*")):
                if path.is_file():
                    info = zipfile.ZipInfo(path.relative_to(build).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return {
        "packageId": manifest["packageId"],
        "kind": manifest["kind"],
        "name": manifest["name"],
        "versionName": manifest["versionName"],
        "versionCode": manifest["versionCode"],
        "minAppVersionCode": manifest["minAppVersionCode"],
        "size": output.stat().st_size,
        "sha256": sha256(output),
        "sourceRepository": manifest["sourceRepository"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "resource.ilunyupack")
    parser.add_argument("--release-output", type=Path)
    args = parser.parse_args()
    result = write_package(args.output.resolve())
    release_output = (args.release_output or args.output.parent / "release.json").resolve()
    write_json(release_output, result)
    print(f"Built {args.output}: {result['size']} bytes, sha256 {result['sha256']}")


if __name__ == "__main__":
    main()
