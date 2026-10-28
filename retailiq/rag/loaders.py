"""Safe, local, multi-format knowledge extraction.

Each yielded TextSection is source-addressable (page, sheet, row, or item).
No remote fetching, macros, or document-embedded code are executed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
import csv
import io
import json
import re
import zipfile

SUPPORTED_FORMATS = frozenset({'.md', '.txt', '.pdf', '.docx', '.csv', '.xlsx', '.json', '.html', '.htm'})
DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS_PER_TABLE = 2500  # avoid embedding entire, accidentally huge spreadsheets
MAX_CELLS_PER_ROW = 40


@dataclass(frozen=True)
class TextSection:
    text: str
    metadata: dict[str, str | int] = field(default_factory=dict)


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.excluded: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.excluded.append(tag)
        if not self.excluded and tag in ('p', 'h1', 'h2', 'h3', 'li', 'tr', 'br'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if self.excluded and self.excluded[-1] == tag:
            self.excluded.pop()
        elif not self.excluded and tag in ('p', 'li', 'tr', 'div', 'h1', 'h2', 'h3'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.excluded:
            self.parts.append(data)

    def text(self):
        return '\n'.join(x.strip() for x in ''.join(self.parts).splitlines() if x.strip())


def _column_to_index(address: str) -> int:
    letters = re.match(r'([A-Z]+)', address.upper())
    if not letters:
        return 0
    out = 0
    for char in letters.group(1):
        out = out * 26 + (ord(char) - 64)
    return out - 1


def _xlsx_rows(path: Path) -> Iterable[tuple[str, int, list[str]]]:
    """Read common XLSX sheet values with stdlib (no macro execution).

    Handles shared strings, inline strings, booleans, numbers and cached formula
    values. Does not evaluate formulas; unsupported/uncached cells remain blank.
    """
    ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
          'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
          'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if 'xl/workbook.xml' not in names or 'xl/_rels/workbook.xml.rels' not in names:
            raise ValueError('Not a valid XLSX workbook')
        shared = []
        if 'xl/sharedStrings.xml' in names:
            ss = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            for item in ss.findall('x:si', ns):
                shared.append(''.join(t.text or '' for t in item.findall('.//x:t', ns)))
        wb = ET.fromstring(archive.read('xl/workbook.xml'))
        relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        targets = {rel.attrib.get('Id'): rel.attrib.get('Target', '') for rel in relationships}
        for s in wb.findall('x:sheets/x:sheet', ns):
            sheet_name = s.attrib['name']
            rid = s.attrib.get('{' + ns['r'] + '}id')
            target = targets.get(rid, '')
            if target.startswith('/'):
                member = target.lstrip('/')
            elif target.startswith('xl/'):
                member = target
            else:
                member = 'xl/' + target.lstrip('./')
            # no traversal outside xl/**; reject external links
            if not member.startswith('xl/') or '..' in Path(member).parts or member not in names:
                continue
            root = ET.fromstring(archive.read(member))
            for row in root.findall('.//x:sheetData/x:row', ns)[:MAX_ROWS_PER_TABLE+1]:
                cells = [''] * MAX_CELLS_PER_ROW
                for cell in row.findall('x:c', ns):
                    col = _column_to_index(cell.attrib.get('r', 'A1'))
                    if col >= MAX_CELLS_PER_ROW:
                        continue
                    typ = cell.attrib.get('t')
                    if typ == 'inlineStr':
                        val = ''.join(t.text or '' for t in cell.findall('.//x:is//x:t', ns))
                    else:
                        elem = cell.find('x:v', ns)
                        val = (elem.text or '') if elem is not None else ''
                        if typ == 's' and val:
                            ix = int(val)
                            val = shared[ix] if 0 <= ix < len(shared) else ''
                        if typ == 'b':
                            val = 'TRUE' if val == '1' else 'FALSE'
                    cells[col] = val
                while cells and not cells[-1]:
                    cells.pop()
                if cells and any(cells):
                    yield sheet_name, int(row.attrib.get('r', '1')), cells


def _table_sections(rows: Iterable[tuple[str, int, list[str]]], label: str) -> list[TextSection]:
    sections = []
    headers: dict[str, list[str]] = {}
    for group, number, values in rows:
        if group not in headers:
            headers[group] = [v or f'Column {i+1}' for i, v in enumerate(values)]
            continue
        if len(sections) >= MAX_ROWS_PER_TABLE:
            break
        fields = [f'{key}: {value}' for key, value in zip(headers[group], values) if value]
        if fields:
            sections.append(TextSection(f'{label} {group} row {number}: ' + '; '.join(fields),
                                        {'sheet' if label == 'Sheet' else 'table': group, 'row': number}))
    return sections


def _json_sections(path: Path) -> list[TextSection]:
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if isinstance(data, list):
        entries = list(enumerate(data))
    elif isinstance(data, dict) and isinstance(data.get('items'), list):
        entries = list(enumerate(data['items']))
    else:
        entries = [(0, data)]
    return [TextSection(json.dumps(value, ensure_ascii=False, sort_keys=True), {'item': index+1})
            for index, value in entries[:MAX_ROWS_PER_TABLE] if value not in (None, '', {}, [])]


def load_file(path: Path, *, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> list[TextSection]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f'Unsupported document format: {ext}')
    if not path.is_file() or path.is_symlink():
        raise ValueError('Expected regular non-symlink document')
    if path.stat().st_size > max_bytes:
        raise ValueError('Document exceeds configured size limit')
    if ext in {'.md', '.txt'}:
        text = path.read_text(encoding='utf-8-sig')
        sections = [TextSection(text)]
    elif ext in {'.html', '.htm'}:
        parser = _HTMLText()
        parser.feed(path.read_text(encoding='utf-8-sig'))
        sections = [TextSection(parser.text())]
    elif ext == '.json':
        sections = _json_sections(path)
    elif ext == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.reader(stream)
            sections = _table_sections((('CSV', n, row[:MAX_CELLS_PER_ROW]) for n, row in enumerate(reader, 1)), 'CSV')
    elif ext == '.xlsx':
        sections = _table_sections(_xlsx_rows(path), 'Sheet')
    elif ext == '.docx':
        from docx import Document
        doc = Document(path)
        sections = [TextSection(p.text, {'paragraph': i})
                    for i, p in enumerate(doc.paragraphs, 1) if p.text.strip()]
        for i, table in enumerate(doc.tables, 1):
            rows = ([c.text.strip() for c in row.cells] for row in table.rows)
            sections += _table_sections(((f'Table {i}', n, cells[:MAX_CELLS_PER_ROW])
                                        for n, cells in enumerate(rows, 1)), 'Table')
    else:  # PDF
        from pypdf import PdfReader
        pdf = PdfReader(path)
        if pdf.is_encrypted:
            raise ValueError('Encrypted PDF is unsupported')
        sections = [TextSection(page.extract_text(extraction_mode='plain') or '', {'page': i})
                    for i, page in enumerate(pdf.pages, 1)]
        if not any(s.text.strip() for s in sections):
            raise ValueError('PDF has no extractable text (scanned PDF requires OCR)')
    return [TextSection(' '.join(section.text.split()) if ext in {'.csv', '.xlsx', '.json'}
                        else section.text.strip(), section.metadata)
            for section in sections if section.text.strip()]
