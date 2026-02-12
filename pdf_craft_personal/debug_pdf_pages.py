#!/usr/bin/env python3
"""
调试PDF页面数量
"""

from pathlib import Path
from pdf_craft.pdf import DefaultPDFHandler

def check_pdf_pages(pdf_path):
    """检查PDF文件的页数"""
    print(f"Checking PDF: {pdf_path}")

    handler = DefaultPDFHandler()
    document = handler.open(Path(pdf_path))
    try:
        total_pages = document.pages_count
        print(f"Total pages in PDF: {total_pages}")
        return total_pages
    finally:
        document.close()

if __name__ == "__main__":
    # 检查各个PDF文件
    pdfs = ["test.pdf", "test.pdf", "test3.pdf", "test4.pdf"]

    for pdf in pdfs:
        if Path(pdf).exists():
            try:
                pages = check_pdf_pages(pdf)
                print(f"{pdf}: {pages} pages")
            except Exception as e:
                print(f"{pdf}: ERROR - {e}")
        else:
            print(f"{pdf}: File not found")
        print()
