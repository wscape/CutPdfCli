#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
toc_detector.py - PDF 문서 내 목차(TOC) 페이지 탐지 및 텍스트 추출 모듈
- pypdf 및 macOS 내장 PDFKit(JXA Fallback)을 통한 PDF 아웃라인 및 본문 스캔
- 목차 키워드 패턴 매칭
- 동일 파일명 .txt 파일 우선 확인 연동
"""

import json
import os
import re
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

from toc_parser import (
    clean_page_text,
    find_matching_txt_file,
    load_toc_from_txt,
)

# 목차 관련 주요 정규표현식
TOC_TITLE_PATTERNS = [
    re.compile(r"^\s*목\s*차\s*$", re.IGNORECASE),
    re.compile(r"^\s*차\s*례\s*$", re.IGNORECASE),
    re.compile(r"^\s*table\s+of\s+contents\s*$", re.IGNORECASE),
    re.compile(r"^\s*contents\s*$", re.IGNORECASE),
    re.compile(r"^\s*content\s*$", re.IGNORECASE),
    re.compile(r"^\s*목\s*차\s*[\(\[].*?[\)\]]\s*$", re.IGNORECASE),
    re.compile(r"^\s*차\s*례\s*[\(\[].*?[\)\]]\s*$", re.IGNORECASE),
    re.compile(r"^\s*table\s+of\s+contents\s*[\(\[].*?[\)\]]\s*$", re.IGNORECASE),
]

TOC_LINE_SUBSTRING_PATTERNS = [
    re.compile(r"(^|\s)(목\s*차|차\s*례)(\s|$)", re.IGNORECASE),
    re.compile(r"\btable\s+of\s+contents\b", re.IGNORECASE),
    re.compile(r"(^|\s)contents(\s|$)", re.IGNORECASE),
]

# 점선이나 페이지 번호가 나열되는 목차 본문 패턴
TOC_BODY_PATTERN = re.compile(r"(\.{3,}|\_{3,}|\-{3,}|\s{3,})\s*\d+\s*$", re.MULTILINE)


def _scan_outline_for_toc(outline, reader):
    """PDF 아웃라인(북마크)에서 목차 페이지를 재귀 탐색합니다."""
    toc_pages = []
    if not outline:
        return toc_pages

    def traverse(items):
        for item in items:
            if isinstance(item, list):
                traverse(item)
            elif hasattr(item, "title") and hasattr(item, "page"):
                title = str(item.title).strip().lower()
                clean_title = re.sub(r"\s+", "", title)
                if any(k in clean_title for k in ["목차", "차례", "tableofcontents", "contents"]):
                    try:
                        page_num = reader.get_destination_page_number(item) + 1
                        if page_num not in toc_pages:
                            toc_pages.append(page_num)
                    except Exception:
                        pass

    try:
        traverse(outline)
    except Exception:
        pass
    return toc_pages


def _check_page_text_for_toc(text: str) -> tuple[bool, str]:
    """페이지 텍스트를 검사하여 목차 페이지인지 판별합니다."""
    if not text:
        return False, ""

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return False, ""

    # 1. 상위 10개 줄에서 단독 목차 타이틀 검사
    for line in lines[:10]:
        for pattern in TOC_TITLE_PATTERNS:
            if pattern.match(line):
                return True, f"제목 '{line}' 감지"

    # 2. 상위 5개 줄에서 포함 형태 검사 + 본문 패턴 확인
    has_body_dots = len(TOC_BODY_PATTERN.findall(text)) >= 2
    for line in lines[:5]:
        for pattern in TOC_LINE_SUBSTRING_PATTERNS:
            if pattern.search(line):
                if len(line) <= 30 or has_body_dots:
                    return True, f"목차 키워드 '{line}' 감지"

    # 3. 만약 점선+숫자 패턴이 아주 많다면(목차 특유의 구조)
    if len(TOC_BODY_PATTERN.findall(text)) >= 5:
        # 본문 어딘가에 목차 키워드가 한 번이라도 등장하면
        if any(p.search(text) for p in TOC_LINE_SUBSTRING_PATTERNS):
            return True, "목차 구조 및 키워드 감지"

    return False, ""


def find_toc_pages_with_pypdf(pdf_path: str) -> dict:
    """pypdf를 사용하여 목차 페이지 번호 및 해당 페이지 텍스트를 추출합니다."""
    reader = pypdf.PdfReader(pdf_path)
    total_pages = len(reader.pages)
    toc_pages = []
    details = []

    # 1. 아웃라인(북마크) 검사
    try:
        outline_pages = _scan_outline_for_toc(reader.outline, reader)
        if outline_pages:
            for p in outline_pages:
                if 1 <= p <= total_pages and p not in toc_pages:
                    toc_pages.append(p)
            details.append(f"TOC page(s) ({', '.join(map(str, outline_pages))}) found in PDF Outline")
    except Exception:
        pass

    # 2. 페이지 텍스트 스캔
    # 보통 목차는 앞쪽 35페이지 이내에 위치
    max_scan_pages = min(total_pages, 35)
    text_detected_pages = []

    last_was_toc = False
    for i in range(max_scan_pages):
        page_num = i + 1
        try:
            page = reader.pages[i]
            text = page.extract_text() or ""
        except Exception:
            continue

        is_toc, reason = _check_page_text_for_toc(text)

        # 연속된 목차 페이지 처리 (이전 페이지가 목차였고, 이번 페이지에도 점선 목차 패턴이 이어지는 경우)
        if not is_toc and last_was_toc:
            body_matches = len(TOC_BODY_PATTERN.findall(text))
            if body_matches >= 3 or ("(계속)" in text or "(cont" in text.lower()):
                is_toc = True
                reason = "연속된 목차 페이지 감지"

        if is_toc:
            if page_num not in toc_pages:
                toc_pages.append(page_num)
            text_detected_pages.append(page_num)
            last_was_toc = True
        else:
            last_was_toc = False

    if text_detected_pages:
        details.append(f"TOC page(s) ({', '.join(map(str, text_detected_pages))}) detected via text analysis")

    toc_pages.sort()

    # 3. 목차 페이지의 실제 텍스트 수집
    toc_texts = {}
    for p_num in toc_pages:
        try:
            raw_text = reader.pages[p_num - 1].extract_text() or ""
            toc_texts[p_num] = clean_page_text(raw_text)
        except Exception:
            toc_texts[p_num] = ""

    return {
        "success": len(toc_pages) > 0,
        "total_pages": total_pages,
        "toc_pages": toc_pages,
        "toc_texts": toc_texts,
        "details": " / ".join(details) if details else "No TOC keywords automatically detected.",
    }


def find_toc_pages_with_macos(pdf_path: str) -> dict:
    """macOS 내장 JXA / PDFKit을 사용하여 목차 페이지 및 텍스트를 추출합니다 (Fallback)."""
    js_code = f"""
    ObjC.import('PDFKit');
    ObjC.import('Foundation');

    var url = $.NSURL.fileURLWithPath({json.dumps(str(Path(pdf_path).resolve()))});
    var doc = $.PDFDocument.alloc.initWithURL(url);
    if (!doc) {{
        JSON.stringify({{ success: false, total_pages: 0, toc_pages: [], toc_texts: {{}}, details: "PDF 문서를 열 수 없습니다." }});
    }} else {{
        var total = doc.pageCount;
        var found = [];
        var maxScan = Math.min(total, 35);
        var pageTexts = {{}};

        // outline 확인
        var root = doc.outlineRoot;
        if (root) {{
            var count = root.numberOfChildren;
            for (var i = 0; i < count; i++) {{
                var child = root.childAtIndex(i);
                var label = ObjC.unwrap(child.label) || "";
                if (/목\\s*차|차\\s*례|table\\s+of\\s+contents|contents/i.test(label)) {{
                    var dest = child.destination;
                    if (dest && dest.page) {{
                        var idx = doc.indexForPage(dest.page);
                        if (idx !== -1 && found.indexOf(idx + 1) === -1) {{
                            found.push(idx + 1);
                        }}
                    }}
                }}
            }}
        }}

        // 텍스트 스캔
        for (var i = 0; i < maxScan; i++) {{
            var p = doc.pageAtIndex(i);
            if (!p) continue;
            var txt = ObjC.unwrap(p.string) || "";
            if (/(^|\\n)\\s*(목\\s*차|차\\s*례|table\\s+of\\s+contents|contents)\\b/i.test(txt)) {{
                var pageNum = i + 1;
                if (found.indexOf(pageNum) === -1) {{
                    found.push(pageNum);
                }}
            }}
        }}

        found.sort(function(a, b){{ return a - b; }});

        // 목차 페이지 텍스트 수집
        for (var i = 0; i < found.length; i++) {{
            var pNum = found[i];
            var p = doc.pageAtIndex(pNum - 1);
            pageTexts[pNum] = p ? (ObjC.unwrap(p.string) || "") : "";
        }}

        JSON.stringify({{
            success: found.length > 0,
            total_pages: total,
            toc_pages: found,
            raw_page_texts: pageTexts,
            details: found.length > 0 ? "macOS PDFKit analysis complete" : "No TOC pages automatically detected."
        }});
    }}
    """
    try:
        res = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", js_code],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip())
            try:
                data["total_pages"] = int(data.get("total_pages", 0))
            except (ValueError, TypeError):
                data["total_pages"] = 0
            raw_texts = data.pop("raw_page_texts", {})
            toc_texts = {}
            for p_num_str, txt in raw_texts.items():
                p_num = int(p_num_str)
                toc_texts[p_num] = clean_page_text(txt)
            data["toc_texts"] = toc_texts
            return data
    except Exception as e:
        return {"success": False, "total_pages": 0, "toc_pages": [], "toc_texts": {}, "details": f"macOS PDFKit error: {e}"}

    return {"success": False, "total_pages": 0, "toc_pages": [], "toc_texts": {}, "details": "PDFKit execution failed"}


def get_pdf_total_pages(pdf_path: str) -> int:
    """PDF 파일의 전체 페이지 수를 구합니다."""
    if PYPDF_AVAILABLE:
        try:
            reader = pypdf.PdfReader(pdf_path)
            return len(reader.pages)
        except Exception:
            pass

    try:
        js_code = f"""
        ObjC.import('PDFKit');
        var url = $.NSURL.fileURLWithPath({json.dumps(str(Path(pdf_path).resolve()))});
        var doc = $.PDFDocument.alloc.initWithURL(url);
        JSON.stringify({{ total: doc ? doc.pageCount : 0 }});
        """
        res = subprocess.run(["osascript", "-l", "JavaScript", "-e", js_code], capture_output=True, encoding="utf-8", errors="replace", timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return int(json.loads(res.stdout.strip()).get("total", 0))
    except Exception:
        pass

    return 0


def find_toc_pages(pdf_path: str) -> dict:
    """
    주어진 PDF 파일에서 목차 페이지 번호 및 해당 페이지들의 텍스트를 추출합니다.
    동일 디렉토리에 동일한 파일명의 .txt 파일이 있는 경우 해당 파일 내용을 기준으로 목차를 생성합니다.
    """
    if not os.path.exists(pdf_path):
        return {
            "success": False,
            "total_pages": 0,
            "toc_pages": [],
            "toc_texts": {},
            "details": "File does not exist.",
        }

    # 1. 동일 폴더 내 동일 파일명의 .txt 파일 우선 확인
    matching_txt = find_matching_txt_file(pdf_path)
    if matching_txt:
        txt_lines = load_toc_from_txt(matching_txt)
        if txt_lines:
            total_pages = get_pdf_total_pages(pdf_path)
            txt_name = Path(matching_txt).name
            return {
                "success": True,
                "total_pages": total_pages,
                "toc_pages": [],
                "toc_texts": {},
                "source_txt": matching_txt,
                "formatted_lines": txt_lines,
                "details": f"Generated from matching text file ({txt_name})",
            }

    if PYPDF_AVAILABLE:
        try:
            return find_toc_pages_with_pypdf(pdf_path)
        except Exception:
            pass

    return find_toc_pages_with_macos(pdf_path)
