import argparse
from pathlib import Path

import pythoncom
import win32com.client


def export_docx_to_pdf(input_docx: Path, output_pdf: Path) -> None:
    input_docx = input_docx.resolve()
    output_pdf = output_pdf.resolve()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = None
    try:
        doc = word.Documents.Open(str(input_docx), ReadOnly=True, AddToRecentFiles=False)
        # 17 = wdExportFormatPDF
        doc.ExportAsFixedFormat(str(output_pdf), 17)
    finally:
        if doc is not None:
            doc.Close(False)
        word.Quit()
        pythoncom.CoUninitialize()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_docx")
    parser.add_argument("output_pdf")
    args = parser.parse_args()
    export_docx_to_pdf(Path(args.input_docx), Path(args.output_pdf))
    print(Path(args.output_pdf).resolve())


if __name__ == "__main__":
    main()
