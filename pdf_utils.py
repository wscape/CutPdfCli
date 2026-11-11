"""
PDF 분석 및 목차(TOC) 페이지 탐지 & 텍스트 추출 모듈
"""

import os
import re
import sys
import unicodedata
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


def clean_page_text(text: str) -> str:
    """페이지 텍스트에서 불필요한 연속 빈 줄과 공백을 정리합니다."""
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned_lines = []
    prev_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank:
            if not prev_blank:
                cleaned_lines.append("")
            prev_blank = True
        else:
            cleaned_lines.append(line)
            prev_blank = False
    return "\n".join(cleaned_lines).strip()


def parse_page_number_from_line(line: str) -> str | None:
    """
    한 줄이 페이지 번호(p.3, 3, page 3, 3쪽 등)를 나타내는지 확인하고 숫자만 남겨서 반환합니다.
    """
    line = line.strip()
    if not line:
        return None

    # 앞뒤 점선, 괄호, 대시, 공백 등 기호 제거
    cleaned = re.sub(r"^[\(\[<{\.·…_–—\-\s]+|[\)\]>}\.·…_–—\-\s]+$", "", line).strip()

    m = re.match(
        r"^(?:p(?:age)?\.?\s*|\s*쪽\s*)?(\d+)(?:\s*(?:p(?:age)?\.?|쪽))?$",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        val = m.group(1)
        # 4자리 이상 큰 숫자(연도 2026 등)는 제외
        if len(val) >= 4:
            return None
        return str(int(val))
    return None


def pad_month_day(text: str) -> str:
    """
    텍스트 내의 월과 일의 숫자가 한 자리일 때 앞에 0을 추가합니다.
    예: 1월 -> 01월, 8일 -> 08일
    """
    if not text:
        return ""
    # 한 자리 월(1~9월) -> 01~09월
    t = re.sub(r"(?<!\d)([1-9])\s*월", r"0\1월", text)
    # 한 자리 일(1~9일) -> 01~09일
    t = re.sub(r"(?<!\d)([1-9])\s*일", r"0\1일", t)
    # 연속 다중 공백 정리
    t = re.sub(r"\s{2,}", " ", t)
    return t


def find_month_info(text: str) -> str:
    """텍스트 내용에서 'X월'(1~12월) 정보를 탐색하며, 한 자리일 경우 앞에 0을 추가합니다."""
    m = re.search(r"(?<!\d)(1[0-2]|[1-9])\s*월", text)
    if m:
        val = int(m.group(1))
        return f"{val:02d}월"
    return ""


def is_table_column_header(line: str) -> bool:
    """
    목차 표의 컬럼 헤더 줄인지 판별합니다.
    예: '순서 / 제목 / 페이지', '제목 | 작곡 | 쪽', 'No. Title Page' 등
    """
    line = line.strip()
    if not line:
        return False
    # 숫자가 포함된 줄은 컬럼 헤더가 아님 (보통 항목이거나 페이지 번호 포함)
    if re.search(r"\d", line):
        return False
    clean = re.sub(r"[\s\W_]+", "", line).lower()
    col_keywords = ["곡명", "제목", "순서", "일자", "작곡", "작사", "title", "page", "페이지", "쪽", "no", "번호"]
    hits = sum(1 for k in col_keywords if k in clean)
    return hits >= 2


def is_toc_header_line(line: str) -> bool:
    """
    한 줄이 목차 제목(헤더)에 해당하는지 판별합니다.
    """
    line = line.strip()
    if not line:
        return False

    # 1. 특수기호나 괄호, 공백을 제거한 순수 텍스트
    clean = re.sub(r"[\s\W_]+", "", line).lower()
    if not clean:
        return False

    exact_headers = {
        "목차", "차례", "목록", "순서",
        "contents", "content", "tableofcontents", "index", "toc",
        "목차안내", "차례안내", "순서안내", "목록안내",
        "전체목차", "세부목차", "목차순서", "순서목차",
        "목차및순서", "순서및목차", "차례및순서", "순서및차례",
        "목차contents", "contents목차", "차례contents", "contents차례",
        "tableofcontents목차", "목차tableofcontents",
        "수록곡목차", "곡목차",
        "순서목록", "프로그램순서", "진행순서",
    }
    if clean in exact_headers:
        return True

    # 2. 앞뒤 특수문자/기호로 둘러싸인 형태 (앞뒤 기호 제거 후)
    # 예: "- 목 차 -", "■ 목차", "◆ 차 례", "★ 목 차 ★", "※ 목차", "< 목 차 >", "[ 목 차 ]"
    unwrapped = re.sub(r"^[\(\[<{《【■◆★●▲▶※\-_=~\s*#|]+|[\)\]>}》】■◆★●▲▶※\-_=~\s*#|]+$", "", line).strip()
    unwrapped_clean = re.sub(r"[\s\W_]+", "", unwrapped).lower()
    if unwrapped_clean in exact_headers:
        return True

    # 3. "X월 목차", "2026년 11월 목차", "11월 수록곡 목차", "11월 곡 목록" 등 연/월/호/구분 + 목차/차례/목록/순서
    toc_core_pattern = r"(?:목\s*차|차\s*례|목\s*록|순\s*서|table\s+of\s+contents|contents|index)"
    if re.search(r"^(?:(?:\d{2,4}년|\d{2,4}[./-])?\s*(?:\d{1,2}월|\d{1,2}[./-])?\s*(?:호)?\s*(?:수록곡|곡|월간|주간)?\s*)+" + toc_core_pattern + r"$", line, re.IGNORECASE):
        return True
        return True

    # 단, 요일 표시나 명시적인 페이지 번호가 들어간 본문 제목 라인은 제외
    if re.search(r"(?:목\s*차|차\s*례|\btable\s+of\s+contents\b|\bcontents\b|\bindex\b)", line, re.IGNORECASE):
        is_item_line = bool(re.search(r"\(\s*(?:월|화|수|목|금|토|일)\s*\)|(?:\bp(?:age)?\.?\s*\d+)|(?:\d+\s*쪽)", line, re.IGNORECASE))
        if not is_item_line and len(line) <= 35:
            return True

    # 5. "목록" 또는 "순서"로 끝나는 짧은 줄 (길이 25자 이하)
    if re.search(r"(?:목\s*록|순\s*서)$", clean):
        is_item_line = bool(re.search(r"\(\s*(?:월|화|수|목|금|토|일)\s*\)|(?:\bp(?:age)?\.?\s*\d+)|(?:\d+\s*쪽)", line, re.IGNORECASE))
        if not is_item_line and len(line) <= 25:
            return True

    return False


def format_toc_by_user_rule(text: str) -> list[str]:
    """
    목차 페이지 텍스트를 사용자의 지정 기준에 맞게 변환합니다:
    1. 타이틀 작업 전 목차 제목 헤더 및 상단 메타데이터 제거
    2. 제목의 한 자리 월/일 숫자에 0 추가 (예: 1일 -> 01일, 8일 -> 08일)
    3. 그다음 페이지 번호 나올 때까지 줄 삭제
    4. 페이지 번호 출력 (숫자만 남김)
    5. 그다음 줄(제목) 출력
    6. 그다음 페이지 번호 나올 때까지 줄 삭제
    7. 페이지 번호 출력 (숫자만 남김)
    8. 끝까지 반복
    """
    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not raw_lines:
        return []

    # 1. 첫 번째 페이지 번호가 등장하기 전에 목차 헤더가 있는지 탐색
    first_page_idx = None
    for idx, line in enumerate(raw_lines):
        if parse_page_number_from_line(line) or re.search(r"(?:[\.·…_–—\-]{2,}|\s{2,})\s*(?:p(?:age)?\.?\s*)?\d+\s*$", line, re.I):
            first_page_idx = idx
            break

    scan_limit = first_page_idx if first_page_idx is not None else len(raw_lines)
    toc_header_idx = None
    for idx in range(scan_limit):
        if is_toc_header_line(raw_lines[idx]):
            toc_header_idx = idx
            break

    # 목차 헤더가 존재하면 그 헤더와 그 이전의 모든 메타데이터 라인을 건너뜀
    if toc_header_idx is not None:
        start_idx = toc_header_idx + 1
    else:
        start_idx = 0

    # 목차 헤더 뒤에 이어지는 추가 목차 헤더나 컬럼 헤더(제목, 페이지 등) 건너뜀
    while start_idx < len(raw_lines):
        line = raw_lines[start_idx]
        if is_toc_header_line(line) or is_table_column_header(line):
            start_idx += 1
        else:
            break

    result = []
    state = "SEEK_TITLE"

    for i in range(start_idx, len(raw_lines)):
        line = raw_lines[i]
        page_val = parse_page_number_from_line(line)

        if state == "SEEK_TITLE":
            # 혹시 남아있는 목차 헤더 또는 표 컬럼 헤더 줄 건너뜀
            if is_toc_header_line(line) or is_table_column_header(line):
                continue

            # 페이지 번호 단독 줄이 제목보다 먼저 나오면 건너뜀
            if page_val:
                continue

            # 한 줄에 제목과 페이지 번호가 합쳐진 경우 (예: '1. Overview .......... 1', '제목 ... p.3', '제목, 3')
            combined_match = re.search(
                r"^(?P<title>.+?)\s*(?:[\.·…_–—\-]{2,}|\s{2,}|\s*,\s*)\s*(?:p(?:age)?\.?\s*)?(?P<page>\d+)\s*$",
                line,
                re.IGNORECASE,
            )
            if combined_match:
                t = combined_match.group("title").strip()
                p = combined_match.group("page").strip()
                t = re.sub(r"[\.·…_–—\-\s,]+$", "", t).strip()
                if is_toc_header_line(t) or is_table_column_header(t):
                    continue
                result.append(t)
                result.append(str(int(p)))
                continue

            # 제목 한 줄 출력
            result.append(line)
            # 그다음 페이지 번호 나올 때까지 줄 삭제 상태로 전환
            state = "SEEK_PAGE"

        elif state == "SEEK_PAGE":
            # 페이지 번호가 나올 때까지 줄 삭제(무시)
            if page_val:
                # 페이지 번호 출력 (숫자만)
                result.append(page_val)
                # 그다음 줄 출력을 위해 SEEK_TITLE로 복귀
                state = "SEEK_TITLE"
            else:
                # 줄 삭제 (무시)
                pass

    # 제목 줄들의 한 자리 월/일 숫자에 0 추가 (예: 1일 -> 01일, 8일 -> 08일)
    # 홀수 인덱스(페이지 번호 줄)이거나 순수 숫자인 라인은 월/일 패딩 제외
    for i in range(len(result)):
        if not (i % 2 == 1 or result[i].isdigit() or re.match(r"^p\.\d+$", result[i], re.I)):
            result[i] = pad_month_day(result[i])

    return result


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
    import subprocess
    import json

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


def find_matching_txt_file(pdf_path: str) -> str | None:
    """
    주어진 PDF 파일과 동일한 디렉토리에 동일한 파일명을 가진 .txt 파일이 있는지 확인합니다.
    macOS NFD/NFC 유니코드 정규화를 지원합니다.
    """
    p = Path(pdf_path).resolve()
    parent = p.parent
    if not parent.exists():
        return None

    target_stem_nfc = unicodedata.normalize("NFC", p.stem)

    try:
        for entry in parent.iterdir():
            if entry.is_file() and entry.suffix.lower() == ".txt":
                entry_stem_nfc = unicodedata.normalize("NFC", entry.stem)
                if entry_stem_nfc == target_stem_nfc:
                    return str(entry.resolve())
    except Exception:
        pass

    return None


def get_pdf_total_pages(pdf_path: str) -> int:
    """PDF 파일의 전체 페이지 수를 구합니다."""
    if PYPDF_AVAILABLE:
        try:
            reader = pypdf.PdfReader(pdf_path)
            return len(reader.pages)
        except Exception:
            pass

    try:
        import subprocess
        import json
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


def load_toc_from_txt(txt_path: str) -> list[str]:
    """
    동일 파일명의 텍스트 파일에서 목차 라인 리스트(제목, 페이지 교대)를 파싱합니다.
    UTF-8, UTF-8-sig, CP949, EUC-KR 인코딩 지원.
    """
    content = ""
    for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
        try:
            with open(txt_path, "r", encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue

    if not content:
        return []

    return format_toc_by_user_rule(content)


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


def sanitize_filename(name: str) -> str:
    """
    파일명으로 사용할 수 없는 문자를 제거하거나 안전한 문자로 치환하며,
    월과 일의 숫자가 한 자리일 때 앞에 0을 추가합니다 (예: 1월 -> 01월, 8일 -> 08일).
    """
    # 월/일 한 자리 숫자 0 패딩
    name = pad_month_day(name)
    # 파일시스템 금지 문자 치환: \ / : * ? " < > |
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", name)
    # 연속 공백 정리 및 양 끝 공백/마침표 제거
    cleaned = re.sub(r"\s+", " ", cleaned).strip(". ")
    return cleaned or "untitled"


def move_source_file_to_folder(source_pdf: str, target_folder: str) -> tuple[str, bool]:
    """
    분리가 성공했을 때 원본 PDF 파일을 생성된 폴더로 이동합니다.
    반환값: (새 파일 경로, 성공 여부)
    """
    import shutil
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


def parse_split_tasks_from_text(formatted_lines: list[str], total_pages: int) -> list[dict]:
    """
    정제된 목차 라인 리스트로부터 PDF 분할 작업 목록을 구성합니다.
    형태: 제목 줄 바로 다음에 숫자(또는 p.숫자) 줄이 오는 패턴 매칭
    각 작업: {"title": str, "start_page": int, "end_page": int}
    """
    try:
        total_pages = int(total_pages)
    except (ValueError, TypeError):
        total_pages = 0

    items = []
    i = 0
    while i < len(formatted_lines) - 1:
        title = formatted_lines[i].strip()
        page_line = formatted_lines[i + 1].strip()

        m = re.match(r"^(?:p(?:age)?\.?\s*)?(\d+)(?:\s*쪽)?$", page_line, re.IGNORECASE)
        if m:
            start_p = int(m.group(1))
            items.append({"title": title, "start_page": start_p})
            i += 2
            continue
        i += 1

    # 시작 페이지 번호 기준으로 정렬 유지하며 end_page 계산
    for idx in range(len(items)):
        start_p = items[idx]["start_page"]
        if idx + 1 < len(items):
            next_start_p = items[idx + 1]["start_page"]
            # 다음 항목의 시작 페이지 바로 전 페이지까지
            end_p = max(start_p, next_start_p - 1)
        else:
            # 마지막 항목은 전체 PDF의 마지막 페이지까지
            end_p = max(start_p, total_pages)
        items[idx]["end_page"] = end_p

    return items


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
    import subprocess
    import json

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
