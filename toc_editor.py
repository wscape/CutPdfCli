#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
toc_editor.py - 목차(TOC) 확인 및 인라인 수정 대화형 TUI 에디터
"""

import re
import shutil
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
    get_key,
    inline_edit_line,
    make_menu_item,
    print_menu,
)


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
            make_menu_item("[↑↓/←→]", "Move"),
            make_menu_item("[Number]", "Jump"),
            make_menu_item("[Esc]", "Back"),
            make_menu_item("[Enter]", "Select"),
            make_menu_item("[Del]", "Delete"),
            make_menu_item("[-/+]", "Page Adj"),
            make_menu_item("[ . ]", "Quit"),
        ]
        menu_lines = format_menu_lines(menu_items)

        # Calculate scrolling window based on terminal height and header/footer lines
        header_lines = 4 + (1 if details else 0)
        cursor_margin = 1  # 터미널 하단 커서 위치용 여유 줄 (화면 밀림/자동 스크롤 방지)
        footer_lines = 2 + len(menu_lines) + (2 if message else 0) + cursor_margin
        term_height = shutil.get_terminal_size((80, 24)).lines
        available_height = max(1, term_height - (header_lines + footer_lines))

        start_win, end_win = compute_scroll_window(total_items, selected_idx, available_height)

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

        print(get_divider("-", COLOR_CYAN))
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

        elif key in ("BACKSPACE", "DELETE", "DEL"):
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

        elif key in ("PAGEUP", "LEFT"):
            if total_items > 0:
                step = max(1, end_win - start_win)
                selected_idx = max(0, selected_idx - step)
            number_buffer = ""

        elif key in ("PAGEDOWN", "RIGHT"):
            if total_items > 0:
                step = max(1, end_win - start_win)
                selected_idx = min(total_items - 1, selected_idx + step)
            number_buffer = ""

        elif key == "HOME":
            selected_idx = 0
            number_buffer = ""

        elif key == "END":
            selected_idx = max(0, total_items - 1)
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
