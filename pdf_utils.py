#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_utils.py - PDF 처리 Facade (Re-export) 모듈
- 하위 호환성을 유지하기 위해 toc_parser, toc_detector, pdf_splitter의 주요 함수를 재익스포트합니다.
"""

from toc_parser import (
    clean_page_text,
    find_matching_txt_file,
    find_month_info,
    format_toc_by_user_rule,
    is_table_column_header,
    is_toc_header_line,
    load_toc_from_txt,
    pad_month_day,
    parse_page_number_from_line,
    parse_split_tasks_from_text,
    sanitize_filename,
)
from toc_detector import (
    PYPDF_AVAILABLE,
    TOC_BODY_PATTERN,
    TOC_LINE_SUBSTRING_PATTERNS,
    TOC_TITLE_PATTERNS,
    _check_page_text_for_toc,
    _scan_outline_for_toc,
    find_toc_pages,
    find_toc_pages_with_macos,
    find_toc_pages_with_pypdf,
    get_pdf_total_pages,
)
from pdf_splitter import (
    move_source_file_to_folder,
    split_pdf,
    split_pdf_with_macos,
    split_pdf_with_pypdf,
)

__all__ = [
    # toc_parser
    "clean_page_text",
    "parse_page_number_from_line",
    "pad_month_day",
    "find_month_info",
    "is_table_column_header",
    "is_toc_header_line",
    "format_toc_by_user_rule",
    "find_matching_txt_file",
    "load_toc_from_txt",
    "sanitize_filename",
    "parse_split_tasks_from_text",
    # toc_detector
    "PYPDF_AVAILABLE",
    "TOC_TITLE_PATTERNS",
    "TOC_LINE_SUBSTRING_PATTERNS",
    "TOC_BODY_PATTERN",
    "_scan_outline_for_toc",
    "_check_page_text_for_toc",
    "find_toc_pages_with_pypdf",
    "find_toc_pages_with_macos",
    "get_pdf_total_pages",
    "find_toc_pages",
    # pdf_splitter
    "move_source_file_to_folder",
    "split_pdf_with_pypdf",
    "split_pdf_with_macos",
    "split_pdf",
]
