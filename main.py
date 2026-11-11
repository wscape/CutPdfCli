#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CutPdfCli (cpc) - Main CLI Entry Point & Orchestrator
- PDF & 폴더 탐색기 CLI 프로그램
- 화살표 키(↑, ↓, ←, →), 번호 입력, 단축키로 파일 탐색 및 TOC 확인/편집
- TOC 기반 PDF 자동 분할 실행
"""

import locale
import os
import re
import sys
from pathlib import Path

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
    copy_to_clipboard,
    get_divider,
    get_key,
)
from explorer import (
    ensure_pdf_folder,
    get_directory_items,
    render_ui,
)
from toc_editor import (
    prompt_confirmation_fallback,
    prompt_confirmation_tui,
    prompt_confirmation_with_edit_tui,
)


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
            for idx, item in enumerate(items):
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
        if selected_num < 0 or selected_num >= len(items):
            print("Please enter a number from the list.")
            continue

        chosen_item = items[selected_num]

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
    # 명령줄 인수 확인 (--help, --version)
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ("--help", "-h"):
            print("Usage: cpc [DIRECTORY]")
            print("\nCutPdfCli (cpc) - Fast CLI tool to split PDF files using table of contents.")
            print("\nArguments:")
            print("  DIRECTORY      Initial directory to open (defaults to current directory)")
            print("\nOptions:")
            print("  -h, --help     Show this help message and exit")
            print("  -v, --version  Show version information")
            return
        if arg in ("--version", "-v"):
            print("cpc 1.0.0")
            return

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

        page_size = render_ui(current_dir, items, selected_idx, message)
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

        elif key in ("PAGEUP", "LEFT"):
            if items:
                selected_idx = max(0, selected_idx - page_size)
            number_buffer = ""

        elif key in ("PAGEDOWN", "RIGHT"):
            if items:
                selected_idx = min(len(items) - 1, selected_idx + page_size)
            number_buffer = ""

        elif key == "HOME":
            selected_idx = 0
            number_buffer = ""

        elif key == "END":
            if items:
                selected_idx = len(items) - 1
            number_buffer = ""

        elif key.isdigit():
            number_buffer += key
            target_idx = int(number_buffer)
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
