#!/usr/bin/env python3
"""
PDF & 폴더 탐색기 CLI 프로그램
- 현재 디렉토리 기준 상위 폴더(..) 및 하위 폴더, PDF 파일 목록 표시
- 화살표 키(↑, ↓) 또는 번호 입력으로 선택
- 폴더 선택 시 해당 디렉토리로 이동
- PDF 파일 선택 시 파일 전체 경로 및 목차(TOC) 페이지 번호 출력
"""

import locale
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path

if sys.platform == "win32":
    import msvcrt
    select = None
    termios = None
    tty = None
else:
    import select
    import termios
    import tty

# --- UTF-8 및 로케일 초기화 (macOS Finder 더블클릭 등 비터미널/최소 환경 지원) ---
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
if not os.environ.get("LANG"):
    os.environ["LANG"] = "ko_KR.UTF-8"
if not os.environ.get("LC_ALL"):
    os.environ["LC_ALL"] = "ko_KR.UTF-8"
if not os.environ.get("LC_CTYPE"):
    os.environ["LC_CTYPE"] = "UTF-8"

# Windows 콘솔 ANSI 이스케이프 시퀀스 활성화
if sys.platform == "win32":
    os.system("")

for _stream in (sys.stdin, sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

for _loc in ("", "ko_KR.UTF-8", "en_US.UTF-8", "C.UTF-8", "UTF-8"):
    try:
        locale.setlocale(locale.LC_ALL, _loc)
        break
    except Exception:
        pass
# -----------------------------------------------------------------------------

import pdf_utils


# ANSI 색상 코드
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_CYAN = "\033[36m"
COLOR_BLUE = "\033[34m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_RED = "\033[31m"
COLOR_REVERSE = "\033[7m"
COLOR_GRAY = "\033[90m"


def get_terminal_width(default: int = 65) -> int:
    """터미널 창의 너비(columns)를 반환합니다. 기본값 65, 최소값 20."""
    try:
        return max(20, shutil.get_terminal_size((default, 24)).columns)
    except Exception:
        return default


def get_divider(char: str = "-", color: str = "") -> str:
    """터미널 창 크기에 맞춘 가로줄을 반환합니다."""
    line = char * get_terminal_width()
    if color:
        return f"{color}{line}{COLOR_RESET}"
    return line


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def get_visible_width(text: str) -> int:
    """ANSI 코드를 제외한 실제 터미널 표시 너비를 계산합니다."""
    clean_text = _ANSI_ESCAPE_RE.sub("", text)
    width = 0
    for ch in clean_text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


# 메뉴 UI 전용 색상 (단축키, 항목명, 구분선 각각 다른 색상)
COLOR_MENU_KEY = f"{COLOR_BOLD}{COLOR_YELLOW}"   # 단축키 색상 (노란색)
COLOR_MENU_NAME = f"{COLOR_BOLD}" 
COLOR_MENU_SEP = f"  {COLOR_BOLD}{COLOR_CYAN}|{COLOR_RESET}  " # 구분선 색상 (회색)


def make_menu_item(key: str, name: str) -> str:
    """단축키와 항목명을 각각의 지정된 색상으로 포맷팅합니다."""
    return f"{COLOR_MENU_KEY}{key}{COLOR_RESET} {COLOR_MENU_NAME}{name}{COLOR_RESET}"


def format_menu_lines(items: list[str], sep: str = COLOR_MENU_SEP, prefix: str = " ") -> list[str]:
    """
    메뉴 항목들을 터미널 너비에 맞춰 배치합니다.
    각 메뉴의 한 칸(셀) 길이를 동일하게 맞추고,
    항목이 중간에 잘려 두 줄에 걸치지 않도록 너비를 초과하면 항목 단위로 다음 줄로 넘깁니다.
    """
    if not items:
        return []

    term_width = get_terminal_width()
    max_item_width = max(get_visible_width(item) for item in items)
    padded_items = [
        item + (" " * (max_item_width - get_visible_width(item)))
        for item in items
    ]

    lines = []
    current_line = ""
    current_width = 0
    sep_width = get_visible_width(sep)
    prefix_width = get_visible_width(prefix)

    for item in padded_items:
        item_width = get_visible_width(item)
        if not current_line:
            current_line = f"{prefix}{item}"
            current_width = prefix_width + item_width
        else:
            if current_width + sep_width + item_width <= term_width:
                current_line += f"{sep}{item}"
                current_width += sep_width + item_width
            else:
                lines.append(current_line.rstrip())
                current_line = f"{prefix}{item}"
                current_width = prefix_width + item_width

    if current_line:
        lines.append(current_line.rstrip())

    return lines


def print_menu(items: list[str], sep: str = COLOR_MENU_SEP, prefix: str = " "):
    """메뉴 항목들을 터미널 너비에 맞게 항목 단위로 줄바꿈하여 출력합니다."""
    for line in format_menu_lines(items, sep, prefix):
        print(line)


def clear_screen():
    """화면 지우기"""
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def get_directory_items(current_dir: str):
    """
    현재 디렉토리에서 표시할 항목들을 가져옵니다.
    반환 형태: list of dict(type='parent'|'dir'|'pdf', name=str, path=str)
    """
    items = []
    current_path = Path(current_dir).resolve()

    # 1. 상위 폴더(..) 확인
    # 루트 디렉토리(/)가 아닌 경우에만 부모 디렉토리가 존재
    if current_path.parent != current_path:
        items.append({
            "type": "parent",
            "name": "..",
            "path": str(current_path.parent),
            "display": "📁 .. (Parent Directory)",
        })

    try:
        entries = list(os.scandir(current_path))
    except PermissionError:
        return items, "Permission denied."

    folders = []
    pdf_files = []

    for entry in entries:
        try:
            entry_name = unicodedata.normalize("NFC", entry.name)
        except Exception:
            entry_name = entry.name

        # 숨김 파일 및 특수 폴더 제외
        if entry_name.startswith(".") or entry_name == "__pycache__":
            continue

        try:
            if entry.is_dir(follow_symlinks=False):
                folders.append({
                    "type": "dir",
                    "name": entry_name,
                    "path": entry.path,
                    "display": f"📁 {entry_name}/",
                })
            elif entry.is_file(follow_symlinks=False) and entry_name.lower().endswith(".pdf"):
                pdf_files.append({
                    "type": "pdf",
                    "name": entry_name,
                    "path": entry.path,
                    "display": f"📄 {entry_name}",
                })
        except OSError:
            continue

    # 이름순 정렬
    folders.sort(key=lambda x: x["name"].lower())
    pdf_files.sort(key=lambda x: x["name"].lower())

    items.extend(folders)
    items.extend(pdf_files)

    return items, None


def _read_raw_key(fd: int) -> str:
    """
    raw 모드 fd에서 키 입력 하나를 읽어 반환합니다.
    화살표 키, Enter, Esc(단독 50ms 감지), Backspace, Delete, 한글 등 지원.
    """
    b = os.read(fd, 32)
    if not b:
        return ""
    if b == b"\x1b":
        # 뒤따르는 ANSI 시퀀스 확인 (50ms 타임아웃)
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            b += os.read(fd, 31)

    if b == b"\x1b":
        return "ESC"
    elif b in (b"\x1b[A", b"\x1bOA"):
        return "UP"
    elif b in (b"\x1b[B", b"\x1bOB"):
        return "DOWN"
    elif b in (b"\x1b[C", b"\x1bOC"):
        return "RIGHT"
    elif b in (b"\x1b[D", b"\x1bOD"):
        return "LEFT"
    elif b in (b"\x1b[H", b"\x1b[1~"):
        return "HOME"
    elif b in (b"\x1b[F", b"\x1b[4~"):
        return "END"
    elif b == b"\x1b[3~":
        return "DELETE"
    elif b in (b"\r", b"\n"):
        return "ENTER"
    elif b in (b"\x7f", b"\x08"):
        return "BACKSPACE"
    elif b == b"\x03":
        return "CTRL_C"
    elif b == b"\x04":
        return "CTRL_D"
    try:
        return b.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _read_win_key() -> str:
    """
    Windows msvcrt 기반 키 입력 처리.
    화살표 키, Enter, ESC, Backspace, Delete, 일반 키 등 지원.
    """
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        scancode = msvcrt.getwch()
        mapping = {
            "H": "UP",
            "P": "DOWN",
            "K": "LEFT",
            "M": "RIGHT",
            "G": "HOME",
            "O": "END",
            "S": "DELETE",
        }
        return mapping.get(scancode, "")
    if ch in ("\r", "\n"):
        return "ENTER"
    elif ch == "\x1b":
        return "ESC"
    elif ch in ("\x08", "\x7f"):
        return "BACKSPACE"
    elif ch == "\x03":
        return "CTRL_C"
    elif ch == "\x04":
        return "CTRL_D"
    return ch


def get_key():
    """
    키 입력을 받아옵니다 (터미널 raw 모드).
    화살표 키, Enter, ESC, Backspace, 일반 키 처리.
    """
    if sys.platform == "win32":
        return _read_win_key()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return _read_raw_key(fd)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def render_ui(current_dir: str, items: list, selected_idx: int, message: str = ""):
    """UI를 렌더링합니다."""
    clear_screen()
    current_path = Path(current_dir).resolve()

    print(get_divider("=", f"{COLOR_BOLD}{COLOR_CYAN}"))
    print(f"{COLOR_BOLD} 📂 Current Directory: {COLOR_YELLOW}{current_path}{COLOR_RESET}")
    print(get_divider("=", f"{COLOR_BOLD}{COLOR_CYAN}"))

    if not items:
        print(f"\n   {COLOR_GRAY}(No folders or PDF files to display){COLOR_RESET}\n")
    else:
        for idx, item in enumerate(items):
            is_selected = (idx == selected_idx)
            prefix = f"{COLOR_CYAN}▶{COLOR_RESET} " if is_selected else "  "
            num_str = f"[{idx + 1:2d}] "

            if item["type"] == "parent":
                label = f"{COLOR_BLUE}{item['display']}{COLOR_RESET}"
            elif item["type"] == "dir":
                label = f"{COLOR_BLUE}{COLOR_BOLD}{item['display']}{COLOR_RESET}"
            else:  # pdf
                label = f"{COLOR_GREEN}{item['display']}{COLOR_RESET}"

            if is_selected:
                print(f"{prefix}{COLOR_REVERSE}{num_str}{item['display']}{COLOR_RESET}")
            else:
                print(f"{prefix}{COLOR_GRAY}{num_str}{COLOR_RESET}{label}")

    print(f"\n{get_divider('-', COLOR_CYAN)}")
    if message:
        print(f" {COLOR_RED}ℹ {message}{COLOR_RESET}")
        print(get_divider("-", COLOR_CYAN))

    menu_items = [
        make_menu_item("[↑/↓]", "Move"),
        make_menu_item("[Enter]", "Select"),
        make_menu_item("[Number]", "Jump"),
        make_menu_item("[.]", "Quit"),
    ]
    print_menu(menu_items)
    print(get_divider("=", COLOR_CYAN))


def copy_to_clipboard(text: str):
    """macOS 환경에서 pbcopy를 통해 텍스트를 클립보드에 복사합니다."""
    import subprocess
    try:
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, close_fds=True)
        process.communicate(text.encode("utf-8", errors="replace"))
        return True
    except Exception:
        return False


def ensure_pdf_folder(pdf_path: str) -> tuple[str, bool]:
    """
    pdf 파일이 있는 폴더에 파일명(확장자 제외)과 동일한 이름의 폴더가 없다면 생성합니다.
    반환값: (생성된/기존_폴더_경로, 새로_생성되었는지_여부)
    """
    path = Path(pdf_path).resolve()
    target_dir = path.parent / path.stem
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        return str(target_dir), True
    return str(target_dir), False


def adjust_all_page_numbers(lines: list[str], delta: int) -> int:
    """
    모든 페이지 번호 라인의 페이지 번호를 delta만큼 증감합니다.
    페이지 번호는 숫자만 유지하며, 최소 1 이상을 유지합니다.
    변경된 항목 수를 반환합니다.
    """
    count = 0
    for idx, line in enumerate(lines):
        m = re.match(r"^(?:p(?:age)?\.?\s*)?(\d+)(?:\s*쪽)?$", line.strip(), re.IGNORECASE)
        if m and (idx % 2 == 1 or line.strip().isdigit()):
            val = int(m.group(1))
            new_val = max(1, val + delta)
            lines[idx] = str(new_val)
            count += 1
    return count


def inline_edit_line(
    initial_text: str,
    prompt_label: str = "Edit",
    return_none_on_cancel: bool = False,
) -> str | None:
    """
    터미널에서 한 줄을 직접 수정할 수 있는 인라인 텍스트 에디터입니다.
    - Enter: 수정 적용 (수정된 텍스트 반환)
    - Esc: 수정 취소 (return_none_on_cancel=True 시 None, 기본값은 initial_text)
    - Backspace: 앞 글자 삭제
    - Delete: 현재 글자 삭제
    - Left/Right: 커서 이동
    - 일반 키: 커서 위치에 글자 삽입
    """
    chars = list(initial_text)
    cursor = len(chars)

    def _process_key(key: str) -> tuple[bool, str | None]:
        nonlocal cursor
        if key == "ENTER":
            return True, "".join(chars).strip()
        elif key in ("ESC", "CTRL_C", "CTRL_D"):
            return True, None if return_none_on_cancel else initial_text
        elif key == "BACKSPACE":
            if cursor > 0:
                chars.pop(cursor - 1)
                cursor -= 1
        elif key == "DELETE":
            if cursor < len(chars):
                chars.pop(cursor)
        elif key == "LEFT":
            if cursor > 0:
                cursor -= 1
        elif key == "RIGHT":
            if cursor < len(chars):
                cursor += 1
        elif key == "HOME":
            cursor = 0
        elif key == "END":
            cursor = len(chars)
        elif isinstance(key, str) and len(key) >= 1 and not key.startswith("\x1b"):
            for ch in key:
                chars.insert(cursor, ch)
                cursor += 1
        return False, None

    def _render_editor():
        before = "".join(chars[:cursor])
        curr_char = chars[cursor] if cursor < len(chars) else " "
        after = "".join(chars[cursor + 1:]) if cursor < len(chars) else ""

        display_str = (
            f"\r\033[2K   {COLOR_CYAN}✏️  [{prompt_label}]{COLOR_RESET} "
            f"{before}{COLOR_REVERSE}{curr_char}{COLOR_RESET}{after}  "
            f"{COLOR_GRAY}(Enter: Apply | Esc: Cancel){COLOR_RESET}"
        )
        sys.stdout.write(display_str)
        sys.stdout.flush()

    if sys.platform == "win32":
        while True:
            _render_editor()
            key = _read_win_key()
            done, res = _process_key(key)
            if done:
                return res

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            _render_editor()
            key = _read_raw_key(fd)
            done, res = _process_key(key)
            if done:
                return res
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _lines_to_sections(lines: list[str]) -> list[dict]:
    """
    평탄화된 lines 리스트([title_0, page_0, title_1, page_1, ...])를
    섹션 딕셔너리 리스트([{"title": str, "page_str": str, "page_num": int}])로 변환합니다.
    """
    sections = []
    i = 0
    while i < len(lines):
        title = lines[i].strip()
        if i + 1 < len(lines):
            page_str = lines[i + 1].strip()
            m = re.search(r"\d+", page_str)
            page_num = int(m.group(0)) if m else 999999
            sections.append({"title": title, "page_str": page_str, "page_num": page_num})
            i += 2
        else:
            sections.append({"title": title, "page_str": "1", "page_num": 1})
            i += 1
    return sections


def _sections_to_lines(sections: list[dict]) -> list[str]:
    """섹션 딕셔너리 리스트를 다시 평탄화된 lines 리스트로 변환합니다."""
    lines = []
    for sec in sections:
        lines.append(sec["title"])
        lines.append(sec["page_str"])
    return lines


def _sort_sections_by_page(sections: list[dict]) -> list[dict]:
    """섹션들을 page_num 기준으로 오름차순 정렬합니다 (안정 정렬)."""
    return sorted(sections, key=lambda s: s["page_num"])


def prompt_confirmation_fallback(formatted_lines: list[str]) -> tuple[str, list[str]]:
    """
    Fallback standard input mode for TOC confirmation and editing.
    """
    lines = list(formatted_lines)
    fb_menu = [
        make_menu_item("[0]", "Proceed"),
        make_menu_item("[Number]", "Edit Line"),
        make_menu_item("[-]", "Page -"),
        make_menu_item("[+]", "Page +"),
        make_menu_item("[Esc/b]", "Back"),
        make_menu_item("[.]", "Quit"),
    ]
    while True:
        print(f"\n{get_divider('-')}")
        print(f" [Select Action]:")
        print_menu(fb_menu, sep="    ", prefix=" ")
        choice = input(" Select (0: Proceed, Number: Edit, -/+: Page Adj, Esc/b: Back, .: Quit): ").strip()

        if choice in ("0", "proceed", "Proceed"):
            return "proceed", lines
        elif choice in ("-", "page -", "page-", "Page -", "Page-", "-1"):
            cnt = adjust_all_page_numbers(lines, -1)
            print(f" ✓ All page numbers decreased by 1 ({cnt} items total).")
            print("\n [Current TOC Content]")
            for idx, l in enumerate(lines):
                print(f"   [{idx + 1:2d}] {l}")
        elif choice in ("+", "page +", "page+", "Page +", "Page+", "+1"):
            cnt = adjust_all_page_numbers(lines, 1)
            print(f" ✓ All page numbers increased by 1 ({cnt} items total).")
            print("\n [Current TOC Content]")
            for idx, l in enumerate(lines):
                print(f"   [{idx + 1:2d}] {l}")
        elif choice.lower() in ("esc", "b", "back", "reselect"):
            return "reselect", lines
        elif choice in (".", "quit", "exit") or choice.lower() in ("quit", "exit"):
            return "quit", lines
        elif choice.isdigit():
            idx_to_edit = int(choice) - 1
            if 0 <= idx_to_edit < len(lines):
                print(f" Current content: {lines[idx_to_edit]}")
                new_text = input(" New content (Cancel: Enter): ").strip()
                if new_text:
                    lines[idx_to_edit] = new_text
                    print(f" ✓ Edit complete: {new_text}")
            else:
                print(f" Invalid line number: {choice}")
        else:
            continue


def prompt_confirmation_with_edit_tui(
    abs_path: str,
    toc_pages: list,
    total_pages: int,
    details: str,
    initial_formatted_lines: list[str],
    source_txt: str | None = None,
) -> tuple[str, list[str]]:
    """
    Interactive TOC editor with the exact same visual style as the file list UI.
    - [ 0] Proceed at the top: selected, then press [Enter] to execute.
    - [ 1..N] Items for each TOC line (file name and page number) with [number] for quick jump.
    - [ N+1] ➕ Add New Section at the end of the list to add new sections.
    - [Enter] to select: executes on [ 0], edits line on [ 1..N], adds item on [ N+1].
    - [⌫] deletes the selected section (both title and page line).
    - [- / +] adjust all page numbers.
    - [Esc] returns to the file selection list.
    - [.] quits program.
    All menu items and messages are in English.
    """
    lines = _sections_to_lines(_sort_sections_by_page(_lines_to_sections(initial_formatted_lines)))
    selected_idx = 0
    message = ""
    number_buffer = ""

    while True:
        clear_screen()
        pdf_name = Path(abs_path).name

        print(get_divider("=", f"{COLOR_BOLD}{COLOR_CYAN}"))
        print(f"{COLOR_BOLD} 📄 Target PDF: {COLOR_GREEN}{pdf_name}{COLOR_RESET}")
        if source_txt:
            txt_name = Path(source_txt).name
            print(f" {COLOR_BOLD}📑 TOC Reference:{COLOR_RESET} {COLOR_YELLOW}{txt_name}{COLOR_RESET} ({total_pages} pages total)")
        elif toc_pages:
            pages_str = ", ".join(f"p.{p}" for p in toc_pages)
            print(f" {COLOR_BOLD}📑 Detected TOC Pages:{COLOR_RESET} {COLOR_YELLOW}{pages_str}{COLOR_RESET} ({total_pages} pages total)")
        else:
            print(f" {COLOR_BOLD}📑 Detected TOC Pages:{COLOR_RESET} {COLOR_YELLOW}None detected{COLOR_RESET} ({total_pages} pages total)")
        if details:
            print(f" {COLOR_GRAY}ℹ {details}{COLOR_RESET}")
        print(get_divider("=", f"{COLOR_BOLD}{COLOR_CYAN}"))

        total_items = 1 + len(lines) + 1  # 0: Proceed, 1..len(lines): TOC items, len(lines)+1: Add New Section
        selected_idx = max(0, min(selected_idx, total_items - 1))

        # Calculate number column width
        num_width = max(2, len(str(total_items - 1)))

        # Menu items and lines formatted to terminal width
        menu_items = [
            make_menu_item("[↑/↓]", "Move"),
            make_menu_item("[Enter]", "Select"),
            make_menu_item("[⌫]", "Delete"),
            make_menu_item("[-/+]", "Page Adj"),
            make_menu_item("[Number]", "Jump"),
            make_menu_item("[Esc]", "Back"),
            make_menu_item("[.]", "Quit"),
        ]
        menu_lines = format_menu_lines(menu_items)

        # Calculate scrolling window based on terminal height and header/footer lines
        header_lines = 4 + (1 if details else 0)
        footer_lines = 3 + len(menu_lines) + (2 if message else 0)
        term_height = shutil.get_terminal_size((80, 24)).lines
        max_display = max(5, term_height - (header_lines + footer_lines + 2))

        if total_items <= max_display:
            start_win = 0
            end_win = total_items
        else:
            half = max_display // 2
            start_win = max(0, min(selected_idx - half, total_items - max_display))
            end_win = min(total_items, start_win + max_display)

        if start_win > 0:
            print(f"   {COLOR_GRAY}▲ ... ({start_win} items above){COLOR_RESET}")

        for idx in range(start_win, end_win):
            is_selected = (idx == selected_idx)
            prefix = f"{COLOR_CYAN}▶{COLOR_RESET} " if is_selected else "  "
            num_str = f"[{idx:{num_width}d}] "

            if idx == 0:
                plain_display = "🚀 Start PDF Split"
                styled_label = f"{COLOR_BLUE}{COLOR_BOLD}{plain_display}{COLOR_RESET}"
            elif idx == len(lines) + 1:
                plain_display = "➕ Add New Section"
                styled_label = f"{COLOR_CYAN}{COLOR_BOLD}{plain_display}{COLOR_RESET}"
            else:
                line_text = lines[idx - 1]
                is_page_num = bool(re.match(r"^(?:p(?:age)?\.?\s*)?\d+(?:\s*쪽)?$", line_text.strip(), re.I)) and ((idx - 1) % 2 == 1 or line_text.strip().isdigit())
                if is_page_num:
                    plain_display = f"📃 Page: {line_text}"
                    styled_label = f"{COLOR_BOLD}{COLOR_YELLOW}{plain_display}{COLOR_RESET}"
                else:
                    plain_display = f"📄 {line_text}"
                    styled_label = f"{COLOR_GREEN}{plain_display}{COLOR_RESET}"

            if is_selected:
                print(f"{prefix}{COLOR_REVERSE}{num_str}{plain_display}{COLOR_RESET}")
            else:
                print(f"{prefix}{COLOR_GRAY}{num_str}{COLOR_RESET}{styled_label}")

        if end_win < total_items:
            print(f"   {COLOR_GRAY}▼ ... ({total_items - end_win} items below){COLOR_RESET}")

        print(f"\n{get_divider('-', COLOR_CYAN)}")
        if message:
            print(f" {COLOR_RED}ℹ {message}{COLOR_RESET}")
            print(get_divider("-", COLOR_CYAN))

        for m_line in menu_lines:
            print(m_line)
        print(get_divider("=", COLOR_CYAN))

        try:
            key = get_key()
        except (KeyboardInterrupt, Exception):
            return "quit", lines

        message = ""

        if key in (".", "CTRL_C", "CTRL_D"):
            return "quit", lines

        elif key == "ESC":
            return "reselect", lines

        elif key in ("-", "_"):
            cnt = adjust_all_page_numbers(lines, -1)
            secs = _sort_sections_by_page(_lines_to_sections(lines))
            lines = _sections_to_lines(secs)
            message = f"All page numbers decreased by 1 ({cnt} items total)."
            number_buffer = ""

        elif key in ("+", "="):
            cnt = adjust_all_page_numbers(lines, 1)
            secs = _sort_sections_by_page(_lines_to_sections(lines))
            lines = _sections_to_lines(secs)
            message = f"All page numbers increased by 1 ({cnt} items total)."
            number_buffer = ""

        elif key in ("BACKSPACE", "DELETE"):
            number_buffer = ""
            if 1 <= selected_idx <= len(lines):
                line_pos = selected_idx - 1
                sec_idx = line_pos // 2
                secs = _lines_to_sections(lines)
                if 0 <= sec_idx < len(secs):
                    del_sec = secs.pop(sec_idx)
                    lines = _sections_to_lines(secs)
                    message = f"Deleted section: '{del_sec['title']}' (Page {del_sec['page_str']})."
                    new_total = 1 + len(lines) + 1
                    if selected_idx >= new_total - 1:
                        selected_idx = max(0, new_total - 2)
            elif selected_idx == 0:
                message = "Cannot delete Proceed option."
            elif selected_idx == len(lines) + 1:
                message = "Cannot delete Add New Section option."

        elif key == "UP":
            if total_items > 0:
                selected_idx = (selected_idx - 1) % total_items
            number_buffer = ""

        elif key == "DOWN":
            if total_items > 0:
                selected_idx = (selected_idx + 1) % total_items
            number_buffer = ""

        elif key.isdigit():
            number_buffer += key
            target_idx = int(number_buffer)
            if 0 <= target_idx < total_items:
                selected_idx = target_idx
            else:
                message = f"Number [{number_buffer}] is out of range."
                number_buffer = ""

        elif key == "ENTER":
            number_buffer = ""
            if selected_idx == 0:
                return "proceed", lines
            elif selected_idx == len(lines) + 1:
                # Add New Section: Step 1 - Section Title / File Name
                new_title = inline_edit_line("", prompt_label="New Title", return_none_on_cancel=True)
                if new_title is None or not new_title.strip():
                    message = "Section addition cancelled."
                    continue
                new_title = new_title.strip()

                # Step 2 - Section Page Number
                secs = _lines_to_sections(lines)
                default_page = (secs[-1]["page_num"] + 1) if secs else 1
                new_page_str = inline_edit_line(str(default_page), prompt_label="New Page", return_none_on_cancel=True)
                if new_page_str is None or not new_page_str.strip():
                    message = "Section addition cancelled."
                    continue

                m = re.search(r"\d+", new_page_str)
                page_val = int(m.group(0)) if m else default_page
                page_str = str(page_val)

                new_sec = {"title": new_title, "page_str": page_str, "page_num": page_val}
                secs.append(new_sec)
                secs = _sort_sections_by_page(secs)
                lines = _sections_to_lines(secs)

                new_sec_idx = secs.index(new_sec)
                selected_idx = 1 + new_sec_idx * 2
                message = f"Added section '{new_title}' at page {page_val}."
            else:
                line_pos = selected_idx - 1
                curr_text = lines[line_pos]
                is_page_line = (line_pos % 2 == 1) or bool(re.match(r"^(?:p(?:age)?\.?\s*)?\d+(?:\s*쪽)?$", curr_text.strip(), re.I))
                prompt_label = "Edit Page" if is_page_line else "Edit Title"
                new_text = inline_edit_line(curr_text, prompt_label=prompt_label)

                if new_text and new_text != curr_text:
                    lines[line_pos] = new_text
                    if is_page_line:
                        sec_idx = line_pos // 2
                        secs = _lines_to_sections(lines)
                        target_sec = secs[sec_idx] if sec_idx < len(secs) else None

                        secs = _sort_sections_by_page(secs)
                        lines = _sections_to_lines(secs)

                        if target_sec and target_sec in secs:
                            new_sec_idx = secs.index(target_sec)
                            selected_idx = 1 + new_sec_idx * 2 + 1
                        message = f"Line [{selected_idx}] updated: {new_text} (auto-sorted by page)."
                    else:
                        message = f"Line [{selected_idx}] updated: {new_text}"
                else:
                    message = f"Line [{selected_idx}] unchanged."


def prompt_confirmation_tui() -> str:
    """호환성을 위한 기존 래퍼 함수"""
    action, _ = prompt_confirmation_with_edit_tui("", [], 0, "", [])
    return action


def execute_pdf_split(
    abs_path: str,
    target_folder: str,
    toc_pages: list,
    toc_texts: dict,
    total_pages: int,
    formatted_lines: list[str] | None = None,
    source_txt: str | None = None,
    use_color: bool = True,
):
    """
    목차 텍스트에서 파일명과 페이지 번호를 참조하여 PDF를 분할하고 대상 폴더에 저장합니다.
    formatted_lines가 제공되면 사용자가 수정한 라인을 그대로 사용합니다.
    """
    if formatted_lines is not None:
        all_formatted_lines = formatted_lines
    else:
        all_formatted_lines = []
        for p_num in toc_pages:
            txt = toc_texts.get(p_num, "")
            if txt.strip():
                lines = pdf_utils.format_toc_by_user_rule(txt)
                all_formatted_lines.extend(lines)

    tasks = pdf_utils.parse_split_tasks_from_text(all_formatted_lines, total_pages)

    if not tasks:
        msg = "⚠️ Could not extract titles and page numbers from TOC text."
        print(f" {COLOR_YELLOW}{msg}{COLOR_RESET}" if use_color else f" {msg}")
        return []

    split_title = f"✂️  Splitting PDF ({len(tasks)} files total)"
    sep = get_divider("-", COLOR_CYAN if use_color else "")
    print(f"\n{sep}")
    print(f" {COLOR_BOLD}{split_title}{COLOR_RESET}" if use_color else f" {split_title}")
    print(f"{sep}")

    def progress_cb(item: dict, curr: int, total: int):
        idx_str = f"[{curr}/{total}]"
        pages_str = f"({item['start_page']}~{item['end_page']}p, {item['page_count']} pages)"
        if item["success"]:
            status_str = f"{COLOR_GREEN}✓ Done{COLOR_RESET}" if use_color else "✓ Done"
            print(f"   {COLOR_CYAN}{idx_str}{COLOR_RESET} {COLOR_BOLD}{item['filename']}{COLOR_RESET} {COLOR_GRAY}{pages_str}{COLOR_RESET} ... {status_str}" if use_color else f"   {idx_str} {item['filename']} {pages_str} ... {status_str}")
        else:
            status_str = f"{COLOR_RED}✗ Failed ({item['error']}){COLOR_RESET}" if use_color else f"✗ Failed ({item['error']})"
            print(f"   {idx_str} {item['filename']} ... {status_str}")

    results = pdf_utils.split_pdf(abs_path, target_folder, tasks, progress_callback=progress_cb)
    success_count = sum(1 for r in results if r["success"])

    print(f"{sep}")
    done_msg = f"✓ Successfully split and saved {success_count} files!"
    print(f" {COLOR_BOLD}{COLOR_GREEN}{done_msg}{COLOR_RESET}" if use_color else f" {done_msg}")
    print(f" 📂 Output folder: {target_folder}")

    # 분리가 성공하면 선택한 원본 파일도 해당 폴더로 이동
    if success_count > 0:
        new_path, moved = pdf_utils.move_source_file_to_folder(abs_path, target_folder)
        if moved:
            move_msg = f"📦 Source file moved to folder: {Path(new_path).name}"
            print(f" {COLOR_BOLD}{COLOR_YELLOW}{move_msg}{COLOR_RESET}" if use_color else f" {move_msg}")
        if source_txt and os.path.exists(source_txt):
            txt_new_path, txt_moved = pdf_utils.move_source_file_to_folder(source_txt, target_folder)
            if txt_moved:
                txt_move_msg = f"📦 TOC text file moved to folder: {Path(txt_new_path).name}"
                print(f" {COLOR_BOLD}{COLOR_YELLOW}{txt_move_msg}{COLOR_RESET}" if use_color else f" {txt_move_msg}")

    return results


def print_toc_texts(toc_pages: list, toc_texts: dict, use_color: bool = True):
    """감지된 목차 페이지들의 텍스트 내용을 사용자 정의 기준에 맞추어 출력합니다."""
    if not toc_pages:
        return

    for p_num in toc_pages:
        text = toc_texts.get(p_num, "")
        header = f"📖 [TOC Page {p_num} Text Content]"
        sep = get_divider("-", COLOR_CYAN if use_color else "")
        print(f"\n{sep}")
        if use_color:
            print(f" {COLOR_BOLD}{COLOR_CYAN}{header}{COLOR_RESET}")
        else:
            print(f" {header}")
        print(f"{sep}")

        if not text.strip():
            msg = "   (No text extracted from this page. It may be an image-based PDF)"
            print(f"{COLOR_GRAY}{msg}{COLOR_RESET}" if use_color else msg)
            continue

        # 사용자의 목차 텍스트 출력 기준 적용
        formatted_lines = pdf_utils.format_toc_by_user_rule(text)
        lines_to_print = formatted_lines if formatted_lines else text.splitlines()

        for idx, line in enumerate(lines_to_print):
            # 페이지 번호 라인은 강조
            is_page_line = bool(re.match(r"^(?:p(?:age)?\.?\s*)?\d+(?:\s*쪽)?$", line.strip(), re.I)) and (idx % 2 == 1 or line.strip().isdigit())
            if is_page_line:
                if use_color:
                    print(f"   {COLOR_BOLD}{COLOR_YELLOW}{line}{COLOR_RESET}")
                else:
                    print(f"   {line}")
            else:
                if use_color:
                    print(f"   {COLOR_BOLD}{line}{COLOR_RESET}")
                else:
                    print(f"   {line}")


def run_fallback_cli(current_dir: str):
    """
    일반 터미널(TUI 미지원 환경)을 위한 표준 번호 입력 방식 fallback
    """
    while True:
        items, error_msg = get_directory_items(current_dir)
        current_path = Path(current_dir).resolve()

        print(f"\n{get_divider('=')}")
        print(f" 📂 Current Directory: {current_path}")
        print(get_divider("="))

        if error_msg:
            print(f" [Warning] {error_msg}")

        if not items:
            print(" (No folders or PDF files to display)")
        else:
            for idx, item in enumerate(items, 1):
                print(f" [{idx:2d}] {item['display']}")

        print(get_divider("-"))
        user_input = input(" Select (Quit: .): ").strip()

        if user_input in (".", "quit", "Quit"):
            print("Program terminated.")
            break

        if not user_input.isdigit():
            print("Please enter a valid number.")
            continue

        selected_num = int(user_input)
        if selected_num < 1 or selected_num > len(items):
            print("Please enter a number from the list.")
            continue

        chosen_item = items[selected_num - 1]

        if chosen_item["type"] in ("parent", "dir"):
            current_dir = chosen_item["path"]
        elif chosen_item["type"] == "pdf":
            abs_path = os.path.abspath(chosen_item["path"])
            copied = copy_to_clipboard(abs_path)

            print(f"\n{get_divider('=')}")
            print(f" 📄 Selected PDF file path:")
            print(f" {abs_path}")
            if copied:
                print(f" (File path copied to clipboard!)")
            print(get_divider("-"))
            print(f" 🔍 Analyzing TOC pages...")

            toc_info = pdf_utils.find_toc_pages(abs_path)
            total_pages = toc_info.get("total_pages", 0)
            toc_pages = toc_info.get("toc_pages", [])
            toc_texts = toc_info.get("toc_texts", {})
            details = toc_info.get("details", "")
            source_txt = toc_info.get("source_txt")

            if source_txt:
                txt_name = Path(source_txt).name
                print(f" 📄 TOC Reference File: {txt_name} ({total_pages} pages total)")
                print(f"    ℹ {details}")
                formatted_lines = list(toc_info.get("formatted_lines", []))
                if formatted_lines:
                    print(f"\n [TOC Content from Text File]")
                    for idx, line in enumerate(formatted_lines):
                        print(f"   {line}")
            elif toc_pages:
                pages_str = ", ".join(f"p.{p}" for p in toc_pages)
                print(f" 📑 Detected TOC Pages: {pages_str} ({total_pages} pages total)")
                print(f"    ℹ {details}")
                # 목차 페이지 텍스트 출력
                print_toc_texts(toc_pages, toc_texts, use_color=False)
                # 목차 라인 리스트 생성
                formatted_lines = []
                for p_num in toc_pages:
                    txt = toc_texts.get(p_num, "")
                    if txt.strip():
                        lines = pdf_utils.format_toc_by_user_rule(txt)
                        formatted_lines.extend(lines)
            else:
                print(f" 📑 TOC Pages: No TOC pages automatically detected. ({total_pages} pages total)")
                print(f"    ℹ {details}")
                formatted_lines = []

            print(get_divider("="))

            # 사용자 확인: 1.Proceed, 2.Edit, 3.Page-, 4.Page+, 5.Reselect
            action, formatted_lines = prompt_confirmation_fallback(formatted_lines)
            if action == "quit":
                print("Program terminated.")
                break
            elif action == "reselect":
                continue
            elif action == "proceed":
                # pdf 파일이 있는 폴더에 파일명과 동일한 폴더가 없다면 생성
                target_folder, created = ensure_pdf_folder(abs_path)
                print(f"\n{get_divider('=')}")
                if created:
                    print(f" ✓ Created folder with the same name:")
                else:
                    print(f" ℹ Folder with the same name already exists:")
                print(f"   📂 {target_folder}")
                print(get_divider("="))

                # PDF 분리해서 생성된 폴더에 저장 (수정된 목차 라인 적용)
                execute_pdf_split(abs_path, target_folder, toc_pages, toc_texts, total_pages, formatted_lines=formatted_lines, source_txt=source_txt, use_color=False)

                sub_choice = input("\n[1] Continue browsing  [2] Quit (Default: 1): ").strip()
                if sub_choice == "2":
                    print("Program terminated.")
                    break


def run():
    # 명령줄 인수로 시작 디렉토리 지정 가능
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        current_dir = os.path.abspath(sys.argv[1])
    else:
        current_dir = os.getcwd()
        # Finder 더블클릭 등으로 실행 시 CWD가 홈 디렉토리($HOME)인 경우가 많음
        # 만약 실행 파일이 위치한 폴더에 PDF가 있고 CWD가 $HOME이라면 실행 파일 디렉토리를 우선 탐색
        try:
            exe_dir = Path(sys.executable).resolve().parent
            home_dir = Path.home().resolve()
            if Path(current_dir).resolve() == home_dir and exe_dir != home_dir:
                if any(p.suffix.lower() == ".pdf" for p in exe_dir.iterdir() if p.is_file()):
                    current_dir = str(exe_dir)
        except Exception:
            pass

    # 터미널이 stdin에 연결되어 있지 않거나 TTY가 아닌 경우 fallback 실행
    if not sys.stdin.isatty():
        run_fallback_cli(current_dir)
        return

    selected_idx = 0
    message = ""
    number_buffer = ""

    while True:
        items, error_msg = get_directory_items(current_dir)
        if error_msg:
            message = error_msg

        if not items:
            selected_idx = 0
        else:
            selected_idx = max(0, min(selected_idx, len(items) - 1))

        render_ui(current_dir, items, selected_idx, message)
        message = ""

        try:
            key = get_key()
        except (KeyboardInterrupt, Exception):
            clear_screen()
            print("Program terminated.")
            break

        if key in (".", "CTRL_C", "CTRL_D"):
            clear_screen()
            print("Program terminated.")
            break

        elif key == "UP":
            if items:
                selected_idx = (selected_idx - 1) % len(items)
            number_buffer = ""

        elif key == "DOWN":
            if items:
                selected_idx = (selected_idx + 1) % len(items)
            number_buffer = ""

        elif key.isdigit():
            number_buffer += key
            target_idx = int(number_buffer) - 1
            if 0 <= target_idx < len(items):
                selected_idx = target_idx
            else:
                message = f"Number {number_buffer} is out of range."
                number_buffer = ""

        elif key == "ENTER":
            number_buffer = ""
            if not items:
                continue

            chosen_item = items[selected_idx]

            if chosen_item["type"] in ("parent", "dir"):
                # 폴더 이동
                target_path = chosen_item["path"]
                if os.path.isdir(target_path) and os.access(target_path, os.R_OK):
                    current_dir = target_path
                    selected_idx = 0
                else:
                    message = f"Cannot access folder: {chosen_item['name']}"
            elif chosen_item["type"] == "pdf":
                # PDF 파일 선택 시 경로 및 목차 페이지 출력
                abs_path = os.path.abspath(chosen_item["path"])
                copied = copy_to_clipboard(abs_path)

                clear_screen()
                print(get_divider("=", f"{COLOR_BOLD}{COLOR_CYAN}"))
                print(f"{COLOR_BOLD}{COLOR_GREEN} 📄 Selected PDF file: {chosen_item['name']}{COLOR_RESET}")
                print(f" {COLOR_BOLD}📂 Full path:{COLOR_RESET} {abs_path}")
                if copied:
                    print(f" {COLOR_YELLOW}✓ File path copied to clipboard.{COLOR_RESET}")
                print(get_divider("-", COLOR_CYAN))
                print(f" {COLOR_BOLD}🔍 Analyzing TOC pages...{COLOR_RESET}")

                toc_info = pdf_utils.find_toc_pages(abs_path)
                total_pages = toc_info.get("total_pages", 0)
                toc_pages = toc_info.get("toc_pages", [])
                toc_texts = toc_info.get("toc_texts", {})
                details = toc_info.get("details", "")
                source_txt = toc_info.get("source_txt")

                # 목차 라인 리스트 생성
                if source_txt and "formatted_lines" in toc_info:
                    formatted_lines = list(toc_info["formatted_lines"])
                else:
                    formatted_lines = []
                    for p_num in toc_pages:
                        txt = toc_texts.get(p_num, "")
                        if txt.strip():
                            lines = pdf_utils.format_toc_by_user_rule(txt)
                            formatted_lines.extend(lines)

                # 사용자 확인 및 수정: 1.Proceed, 2.Edit, 3.Page-, 4.Page+, 5.Reselect
                action, formatted_lines = prompt_confirmation_with_edit_tui(
                    abs_path, toc_pages, total_pages, details, formatted_lines, source_txt=source_txt
                )

                if action == "quit":
                    clear_screen()
                    print("Program terminated.")
                    break
                elif action == "reselect":
                    continue
                elif action == "proceed":
                    # pdf 파일이 있는 폴더에 파일명과 동일한 폴더가 없다면 생성
                    target_folder, created = ensure_pdf_folder(abs_path)

                    clear_screen()
                    print(get_divider("=", f"{COLOR_BOLD}{COLOR_CYAN}"))
                    print(f"{COLOR_BOLD} 📄 Target file: {COLOR_GREEN}{chosen_item['name']}{COLOR_RESET}")
                    if created:
                        print(f" {COLOR_GREEN}✓ Created folder with the same name:{COLOR_RESET}")
                    else:
                        print(f" {COLOR_YELLOW}ℹ Folder with the same name already exists:{COLOR_RESET}")
                    print(f"   📂 {COLOR_BOLD}{COLOR_CYAN}{target_folder}{COLOR_RESET}")
                    print(get_divider("=", f"{COLOR_BOLD}{COLOR_CYAN}"))

                    # PDF 분리해서 생성된 폴더에 저장 (수정된 목차 라인 적용)
                    execute_pdf_split(abs_path, target_folder, toc_pages, toc_texts, total_pages, formatted_lines=formatted_lines, source_txt=source_txt, use_color=True)
                    print(f"{get_divider('=', f'{COLOR_BOLD}{COLOR_CYAN}')}\n")

                    print(f" Press {COLOR_BOLD}[Enter]{COLOR_RESET} or any key to continue browsing. (Quit: {COLOR_BOLD}.{COLOR_RESET})")
                    try:
                        next_key = get_key()
                        if next_key in (".", "CTRL_C", "CTRL_D"):
                            clear_screen()
                            print(f"Output folder: {target_folder}")
                            print("Program terminated.")
                            break
                    except KeyboardInterrupt:
                        clear_screen()
                        print("Program terminated.")
                        break


def main():
    """Main entry point."""
    run()


if __name__ == "__main__":
    main()
