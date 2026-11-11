#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui_common.py - 터미널 공통 UI, ANSI 색상 팔레트, 키보드 입력 및 스크롤 유틸리티
"""

import os
import re
import select
import shutil
import subprocess
import sys
import unicodedata

if sys.platform != "win32":
    import termios
    import tty
else:
    import msvcrt


# =============================================================================
# ANSI 색상 코드 (밝은 테마 & 어두운 테마 모두 가독성이 뛰어난 256컬러 유니버설 팔레트)
# 흰색 배경(#FFFFFF)과 검은색 배경(#000000) 모두에서 명도 대비(Contrast Ratio) 3.5:1 이상 확보
# =============================================================================
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_DIM = "\033[2m"
COLOR_CYAN = "\033[38;5;31m"     # Deep Teal / Medium Cyan (흰색/검정 배경 모두 구분되는 청록)
COLOR_BLUE = "\033[38;5;33m"     # Dodger Blue (어두운 배경에서도 묻히지 않는 산뜻한 블루)
COLOR_GREEN = "\033[38;5;29m"    # Sea Green / Emerald (밝은 배경에서도 또렷한 짙은 녹색)
COLOR_YELLOW = "\033[38;5;166m"  # Warm Amber / Dark Gold (흰색 배경에서도 선명하게 읽히는 호박색/금색)
COLOR_RED = "\033[38;5;160m"     # Crimson Red (선명한 빨간색)
COLOR_REVERSE = "\033[7m"        # 색상 반전 (터미널 테마에 맞춰 자동 반전)
COLOR_GRAY = "\033[38;5;244m"    # Mid Gray (양쪽 배경 모두에서 적절한 보조 텍스트 회색)

# 메뉴 UI 전용 색상 (단축키, 항목명, 구분선 각각 다른 색상)
COLOR_MENU_KEY = f"{COLOR_BOLD}{COLOR_YELLOW}"   # 단축키 색상 (노란색/호박색)
COLOR_MENU_NAME = f"{COLOR_BOLD}" 
COLOR_MENU_SEP = f" {COLOR_BOLD}{COLOR_CYAN}|{COLOR_RESET} " # 구분선 색상 (청록색)


# =============================================================================
# 터미널 크기 및 레이아웃 헬퍼
# =============================================================================
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


# =============================================================================
# 키보드 입력 핸들러 (Cross-platform raw key input)
# =============================================================================
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
    elif b in (b"\x1b[5~", b"\x1b[[5~", b"\x1b[5;2~", b"\x1b[5;5~"):
        return "PAGEUP"
    elif b in (b"\x1b[6~", b"\x1b[[6~", b"\x1b[6;2~", b"\x1b[6;5~"):
        return "PAGEDOWN"
    elif b == b"\x1b[3~" or (b.startswith(b"\x1b[3") and b.endswith(b"~")) or b == b"\x1b[P":
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
            "I": "PAGEUP",
            "Q": "PAGEDOWN",
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


def get_key() -> str:
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


# =============================================================================
# 스크롤 윈도우 계산
# =============================================================================
def compute_scroll_window(total_items: int, selected_idx: int, available_height: int) -> tuple[int, int]:
    """
    터미널 가용 높이에 맞추어 (start_idx, end_idx) 스크롤 윈도우 범위를 계산합니다.
    스크롤 인디케이터(▲ / ▼)가 필요한 경우 인디케이터가 차지하는 행 수(각 1줄)를 고려합니다.
    """
    if total_items <= 0:
        return 0, 0
    if total_items <= available_height:
        return 0, total_items

    # 윈도우 크기는 가용 높이에서 인디케이터(최대 2줄)를 뺀 값 (최소 1개 이상)
    window_size = max(1, available_height - 2)

    # selected_idx가 가급적 중앙에 오도록 시작 위치 계산
    start = selected_idx - (window_size // 2)
    start = max(0, min(start, total_items - window_size))
    end = min(total_items, start + window_size)

    # 위쪽이나 아래쪽 인디케이터 중 한 쪽만 필요한 경우 1줄 더 표시
    if start == 0 and end < total_items and (end - start + 1) <= (available_height - 1):
        end = min(total_items, end + 1)
    elif end == total_items and start > 0 and (end - start + 1) <= (available_height - 1):
        start = max(0, start - 1)

    return start, end


# =============================================================================
# 인라인 텍스트 에디터 (Terminal Inline Line Editor)
# =============================================================================
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
    - Home/End: 줄 시작/끝 이동
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


# =============================================================================
# 클립보드 헬퍼
# =============================================================================
def copy_to_clipboard(text: str) -> bool:
    """macOS 환경에서 pbcopy를 통해 텍스트를 클립보드에 복사합니다."""
    try:
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, close_fds=True)
        process.communicate(text.encode("utf-8", errors="replace"))
        return True
    except Exception:
        return False
