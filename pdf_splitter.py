#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_splitter.py - PDF 페이지 분할, 저장 및 원본 파일 이동 모듈
- pypdf 및 macOS 내장 PDFKit(JXA Fallback)을 사용한 개별 PDF 생성
- 작업 목록(시작 페이지 ~ 종료 페이지) 기준 페이지 추출
- 중복 파일명 자동 넘버링 (_1, _2 ...)
- 분할 성공 시 원본 파일 타깃 폴더로 이동
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 가상환경이 프로젝트 내에 존재할 경우 sys.path에 추가하여 pypdf 자동 로드 (PyInstaller 번들 실행 시 제외)
if not getattr(sys, "frozen", False):
    _venv_lib = Path(__file__).resolve().parent / ".venv" / "lib"
    if _venv_lib.exists():
        for _site in _venv_lib.glob("python*/site-packages"):
            if str(_site) not in sys.path:
                sys.path.insert(0, str(_site))

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

from toc_parser import sanitize_filename


def move_source_file_to_folder(source_pdf: str, target_folder: str) -> tuple[str, bool]:
    """
    분리가 성공했을 때 원본 PDF 파일을 생성된 폴더로 이동합니다.
    반환값: (새 파일 경로, 성공 여부)
    """
    src_path = Path(source_pdf).resolve()
    dst_dir = Path(target_folder).resolve()

    if not src_path.exists():
        return "", False

    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_file = dst_dir / src_path.name

    # 중복 방지 (기존 파일이 이미 존재할 경우)
    if dst_file.exists() and dst_file.resolve() != src_path.resolve():
        counter = 1
        stem = src_path.stem
        ext = src_path.suffix
        while dst_file.exists():
            dst_file = dst_dir / f"{stem}_original_{counter}{ext}"
            counter += 1

    try:
        shutil.move(str(src_path), str(dst_file))
        return str(dst_file), True
    except Exception:
        return "", False


def split_pdf_with_pypdf(source_pdf: str, output_dir: str, tasks: list[dict], progress_callback=None) -> list[dict]:
    """pypdf를 사용하여 PDF를 분할 저장합니다."""
    reader = pypdf.PdfReader(source_pdf)
    total_pages = len(reader.pages)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for idx, task in enumerate(tasks, 1):
        title = task["title"]
        start_page = task["start_page"]
        end_page = task["end_page"]

        safe_name = sanitize_filename(title)
        out_filename = f"{safe_name}.pdf"
        out_path = out_dir / out_filename

        # 중복 파일명 방지
        counter = 1
        while out_path.exists():
            out_filename = f"{safe_name}_{counter}.pdf"
            out_path = out_dir / out_filename
            counter += 1

        writer = pypdf.PdfWriter()
        # 안전한 페이지 인덱스 계산
        s_idx = max(0, min(total_pages - 1, start_page - 1))
        e_idx = max(s_idx + 1, min(total_pages, end_page))

        for p in range(s_idx, e_idx):
            writer.add_page(reader.pages[p])

        success = False
        error_msg = ""
        try:
            with open(out_path, "wb") as f:
                writer.write(f)
            success = True
        except Exception as e:
            error_msg = str(e)

        page_count = len(writer.pages)
        res_item = {
            "index": idx,
            "title": title,
            "filename": out_filename,
            "path": str(out_path),
            "start_page": start_page,
            "end_page": end_page,
            "page_count": page_count,
            "success": success,
            "error": error_msg,
        }
        results.append(res_item)

        if progress_callback:
            progress_callback(res_item, idx, len(tasks))

    return results


def split_pdf_with_macos(source_pdf: str, output_dir: str, tasks: list[dict], progress_callback=None) -> list[dict]:
    """macOS 내장 JXA / PDFKit을 사용하여 PDF를 분할 저장합니다 (Fallback)."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for idx, task in enumerate(tasks, 1):
        title = task["title"]
        start_page = task["start_page"]
        end_page = task["end_page"]

        safe_name = sanitize_filename(title)
        out_filename = f"{safe_name}.pdf"
        out_path = out_dir / out_filename

        counter = 1
        while out_path.exists():
            out_filename = f"{safe_name}_{counter}.pdf"
            out_path = out_dir / out_filename
            counter += 1

        js_code = f"""
        ObjC.import('PDFKit');
        ObjC.import('Foundation');

        var srcUrl = $.NSURL.fileURLWithPath({json.dumps(str(Path(source_pdf).resolve()))});
        var dstUrl = $.NSURL.fileURLWithPath({json.dumps(str(out_path.resolve()))});
        var srcDoc = $.PDFDocument.alloc.initWithURL(srcUrl);

        if (!srcDoc) {{
            JSON.stringify({{ success: false, error: "Cannot open source PDF" }});
        }} else {{
            var total = srcDoc.pageCount;
            var newDoc = $.PDFDocument.alloc.init;
            var s = Math.max(0, {start_page} - 1);
            var e = Math.min(total, {end_page});
            var added = 0;

            for (var p = s; p < e; p++) {{
                var page = srcDoc.pageAtIndex(p);
                if (page) {{
                    newDoc.insertPageAtIndex(page, added);
                    added++;
                }}
            }}
            var ok = newDoc.writeToURL(dstUrl);
            JSON.stringify({{ success: Boolean(ok), page_count: added }});
        }}
        """
        success = False
        error_msg = ""
        page_count = 0
        try:
            res = subprocess.run(
                ["osascript", "-l", "JavaScript", "-e", js_code],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout.strip())
                success = data.get("success", False)
                page_count = data.get("page_count", 0)
                error_msg = data.get("error", "")
        except Exception as e:
            error_msg = str(e)

        res_item = {
            "index": idx,
            "title": title,
            "filename": out_filename,
            "path": str(out_path),
            "start_page": start_page,
            "end_page": end_page,
            "page_count": page_count,
            "success": success,
            "error": error_msg,
        }
        results.append(res_item)

        if progress_callback:
            progress_callback(res_item, idx, len(tasks))

    return results


def split_pdf(source_pdf: str, output_dir: str, tasks: list[dict], progress_callback=None) -> list[dict]:
    """
    주어진 작업 목록에 따라 PDF 파일을 분할하여 대상 폴더에 저장합니다.
    """
    if PYPDF_AVAILABLE:
        try:
            return split_pdf_with_pypdf(source_pdf, output_dir, tasks, progress_callback)
        except Exception:
            pass

    return split_pdf_with_macos(source_pdf, output_dir, tasks, progress_callback)
