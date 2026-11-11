#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
explorer.py - 파일 및 디렉토리 탐색 화면 UI 및 파일 시스템 탐색 로직
"""

import os
import shutil
import unicodedata
from pathlib import Path

from ui_common import (
    COLOR_RESET,
    COLOR_BOLD,
    COLOR_CYAN,
    COLOR_BLUE,
    COLOR_GREEN,
    COLOR_YELLOW,
    COLOR_RED,
    COLOR_REVERSE,
    COLOR_GRAY,
    clear_screen,
    compute_scroll_window,
    format_menu_lines,
    get_divider,
    make_menu_item,
)


def get_directory_items(current_dir: str):
    """
    현재 디렉토리에서 표시할 항목들을 가져옵니다.
    반환 형태: (list of dict(type='parent'|'dir'|'pdf', name=str, path=str), error_msg)
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


def render_ui(current_dir: str, items: list, selected_idx: int, message: str = "") -> int:
    """파일 탐색기 UI를 렌더링하고 한 번에 표시된 항목 수(페이지 크기)를 반환합니다."""
    clear_screen()
    current_path = Path(current_dir).resolve()

    print(get_divider("=", f"{COLOR_BOLD}{COLOR_CYAN}"))
    print(f"{COLOR_BOLD} 📂 Current Directory: {COLOR_YELLOW}{current_path}{COLOR_RESET}")
    print(get_divider("=", f"{COLOR_BOLD}{COLOR_CYAN}"))

    menu_items = [
        make_menu_item("[↑↓/←→]", "Move"),
        make_menu_item("[Number]", "Jump"),
        make_menu_item("[Enter]", "Select"),
        make_menu_item("[ . ]", "Quit"),
    ]
    menu_lines = format_menu_lines(menu_items)

    header_lines = 3
    cursor_margin = 1  # 터미널 하단 커서 위치용 여유 줄 (화면 밀림/자동 스크롤 방지)
    footer_lines = 2 + len(menu_lines) + (2 if message else 0) + cursor_margin
    term_height = shutil.get_terminal_size((80, 24)).lines
    available_height = max(1, term_height - (header_lines + footer_lines))

    if not items:
        print(f"\n   {COLOR_GRAY}(No folders or PDF files to display){COLOR_RESET}\n")
        page_size = 1
    else:
        num_width = max(2, len(str(len(items) - 1)))
        start_win, end_win = compute_scroll_window(len(items), selected_idx, available_height)
        page_size = max(1, end_win - start_win)

        if start_win > 0:
            print(f"   {COLOR_GRAY}▲ ... ({start_win} items above){COLOR_RESET}")

        for idx in range(start_win, end_win):
            item = items[idx]
            is_selected = (idx == selected_idx)
            prefix = f"{COLOR_CYAN}▶{COLOR_RESET} " if is_selected else "  "
            num_str = f"[{idx:{num_width}d}] "

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

        if end_win < len(items):
            print(f"   {COLOR_GRAY}▼ ... ({len(items) - end_win} items below){COLOR_RESET}")

    print(get_divider("-", COLOR_CYAN))
    if message:
        print(f" {COLOR_RED}ℹ {message}{COLOR_RESET}")
        print(get_divider("-", COLOR_CYAN))

    for m_line in menu_lines:
        print(m_line)
    print(get_divider("=", COLOR_CYAN))

    return page_size
