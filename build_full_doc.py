# -*- coding: utf-8 -*-
"""
Builder for the PDP presentation document "PDP Presentation: AI Unit Test Assistant".

Reads the sections from content/en/*.md (Part A, English) and content/ru/*.md
(Part B, Russian), in file-name order, and writes one styled .docx with:
- a title page
- a clickable table of contents, generated from the "# " and "## " headings
- a per-page header link back to the contents
- diagrams: ![caption](images/<name>.png), rendered first by build_diagrams.py
- tables, code blocks, callouts (> ...), bullets, numbered lists

Markdown subset: "# Section {#anchor}" once per file (the anchor is optional and
otherwise derived from the file name), "## ... " / "### ... ", pipe tables,
``` fences, "> " callouts, "- " bullets, "1. " numbers, **bold**, `code`.

Run:  python build_diagrams.py && python build_full_doc.py
"""

import itertools
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).parent
CONTENT_DIR = ROOT / "content"
OUT_PATH = ROOT / "PDP_Presentation_AI_Unit_Test_Assistant.docx"

PARTS = [
    ("en", "Part A — English", "Contents", "↑ Contents", "Back to contents"),
    ("ru", "Часть B — Русская версия", "Содержание", "↑ Содержание", "Вернуться к содержанию"),
]

# Palette ------------------------------------------------------------------
NAVY = RGBColor(0x1F, 0x38, 0x64)
LINK = "1155CC"
CODE_FILL = "F4F4F4"
NOTE_FILL = "FFF6E0"
HEADER_FILL = "2E5496"
ALT_FILL = "EDF2F9"
CONTENT_WIDTH = 6.5  # inches (Letter, 1" margins)

doc = Document()
_bid = itertools.count(1)

section = doc.sections[0]
section.page_width = Inches(8.5)
section.page_height = Inches(11)
for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
    setattr(section, side, Inches(1))
section.different_first_page_header_footer = True

normal = doc.styles["Normal"]
normal.font.name = "Arial"
normal.font.size = Pt(11)
normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
for level, size in [(1, 18), (2, 14), (3, 12), (4, 11)]:
    style = doc.styles[f"Heading {level}"]
    style.font.name = "Arial"
    style.font.size = Pt(size)
    style.font.bold = True
    style.font.color.rgb = NAVY


# Low-level XML helpers ------------------------------------------------------
def set_shading(element_pr, fill):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    element_pr.append(shd)


def shade_paragraph(p, fill):
    set_shading(p._p.get_or_add_pPr(), fill)


def shade_cell(cell, fill):
    set_shading(cell._tc.get_or_add_tcPr(), fill)


def paragraph_border(p, sides, color="2E5496", size=12, space=6):
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    for side in sides:
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), str(space))
        el.set(qn("w:color"), color)
        pBdr.append(el)
    pPr.append(pBdr)


def add_bookmark(paragraph, name):
    bid = next(_bid)
    p = paragraph._p
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bid))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bid))
    pPr = p.find(qn("w:pPr"))
    if pPr is not None:
        pPr.addnext(start)
    else:
        p.insert(0, start)
    p.append(end)


def add_internal_link(paragraph, anchor, text, bold=False, size=None, color=LINK):
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("w:anchor"), anchor)
    run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    rStyle = OxmlElement("w:rStyle")
    rStyle.set(qn("w:val"), "Hyperlink")
    rPr.append(rStyle)
    c = OxmlElement("w:color")
    c.set(qn("w:val"), color)
    rPr.append(c)
    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rPr.append(u)
    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"), "Arial")
    rFonts.set(qn("w:hAnsi"), "Arial")
    rPr.append(rFonts)
    if bold:
        rPr.append(OxmlElement("w:b"))
    if size:
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), str(int(size * 2)))
        rPr.append(sz)
    run.append(rPr)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    run.append(t)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


# Inline markdown: **bold**, *italic* and `code` -------------------------------
_INLINE = re.compile(r"(\*\*.+?\*\*|\*[^*\s][^*]*?\*|`[^`]+`)")


def add_inline(paragraph, text):
    for part in _INLINE.split(text):
        if not part:
            continue
        if len(part) >= 4 and part.startswith("**") and part.endswith("**"):
            r = paragraph.add_run(part[2:-2])
            r.bold = True
        elif len(part) >= 3 and part.startswith("*") and part.endswith("*"):
            r = paragraph.add_run(part[1:-1])
            r.italic = True
        elif len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            r = paragraph.add_run(part[1:-1])
            r.font.name = "Consolas"
            r.element.rPr.rFonts.set(qn("w:hAnsi"), "Consolas")
            r.font.size = Pt(9.5)
        else:
            paragraph.add_run(part)


def clean_heading(text):
    return text.replace("**", "").replace("`", "").strip()


# Block emitters --------------------------------------------------------------
def emit_heading(level, text, anchor=None):
    p = doc.add_heading(clean_heading(text), level=level)
    if anchor:
        add_bookmark(p, anchor)
    return p


def emit_paragraph(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    if text.lstrip().startswith("**Q:**"):
        p.paragraph_format.space_before = Pt(8)
    add_inline(p, text)
    return p


def emit_bullet(text, level=0):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(2)
    if level >= 1:
        p.paragraph_format.left_indent = Inches(0.75)
    add_inline(p, text)
    return p


def emit_numbered(num, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.left_indent = Inches(0.5)
    p.paragraph_format.first_line_indent = Inches(-0.25)
    r = p.add_run(f"{num}. ")
    r.bold = True
    add_inline(p, text)
    return p


def emit_code(code_lines):
    while code_lines and code_lines[0].strip() == "":
        code_lines.pop(0)
    while code_lines and code_lines[-1].strip() == "":
        code_lines.pop()
    n = len(code_lines)
    for i, line in enumerate(code_lines):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_before = Pt(8 if i == 0 else 0)
        pf.space_after = Pt(8 if i == n - 1 else 0)
        pf.left_indent = Inches(0.12)
        pf.line_spacing = 1.0
        shade_paragraph(p, CODE_FILL)
        run = p.add_run(line if line != "" else " ")
        run.font.name = "Consolas"
        run.element.rPr.rFonts.set(qn("w:hAnsi"), "Consolas")
        run.font.size = Pt(9)


def emit_callout(lines):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.left_indent = Inches(0.1)
    shade_paragraph(p, NOTE_FILL)
    paragraph_border(p, ["left"], color="E0A800", size=24, space=8)
    for j, ln in enumerate(lines):
        if j > 0:
            p.add_run().add_break()
        add_inline(p, ln)


def emit_image(caption, rel_path):
    path = CONTENT_DIR / rel_path
    if not path.exists():
        raise FileNotFoundError(f"{rel_path}: run build_diagrams.py first")
    doc.add_picture(str(path), width=Inches(CONTENT_WIDTH))
    picture = doc.paragraphs[-1]
    picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
    picture.paragraph_format.space_before = Pt(6)
    picture.paragraph_format.space_after = Pt(2)
    if caption:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(12)
        r = p.add_run(caption)
        r.italic = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)


def emit_table(tbl_lines):
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in tbl_lines]
    if len(rows) < 2:
        return
    header, data = rows[0], rows[2:]  # rows[1] is the --- separator
    ncols = len(header)
    width = round(CONTENT_WIDTH / ncols, 3)

    table = doc.add_table(rows=1, cols=ncols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.allow_autofit = False
    for i, cell in enumerate(table.rows[0].cells):
        shade_cell(cell, HEADER_FILL)
        cell.width = Inches(width)
        para = cell.paragraphs[0]
        para.paragraph_format.space_after = Pt(0)
        run = para.add_run(clean_heading(header[i]) if i < len(header) else "")
        run.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.size = Pt(10)
    for ridx, row in enumerate(data):
        for i, cell in enumerate(table.add_row().cells):
            cell.width = Inches(width)
            if ridx % 2 == 1:
                shade_cell(cell, ALT_FILL)
            para = cell.paragraphs[0]
            para.paragraph_format.space_after = Pt(0)
            add_inline(para, row[i] if i < len(row) else "")
            for run in para.runs:
                if run.font.size is None:
                    run.font.size = Pt(9.5)
    table.style = "Table Grid"
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


# Markdown renderer -----------------------------------------------------------
_H = re.compile(r"^(#{1,4})\s+(.*)$")
_ANCHOR = re.compile(r"\s*\{#([\w-]+)\}\s*$")
_BULLET = re.compile(r"^(\s*)[-*]\s+(.*)$")
_NUM = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_SEP = re.compile(r"^[\s|:\-]+$")
_IMG = re.compile(r"^!\[(.*?)\]\((.+?)\)$")


def is_block_start(s, raw):
    return (
        s == ""
        or s.startswith("```")
        or s.startswith("|")
        or s.startswith(">")
        or s.startswith("![")
        or _H.match(s)
        or _BULLET.match(raw)
        or _NUM.match(raw)
    )


def split_heading(text):
    """'Title {#anchor}' -> ('Title', 'anchor' or None)."""
    m = _ANCHOR.search(text)
    if m:
        return text[: m.start()].rstrip(), m.group(1)
    return text, None


def render_markdown(md_text, anchors):
    """Render one section. ``anchors`` maps heading text -> bookmark name for the TOC."""
    lines = md_text.replace("\r\n", "\n").split("\n")
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()

        if s.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            emit_code(buf)
            continue

        if s.startswith("|") and i + 1 < n and _SEP.match(lines[i + 1].strip()) and "-" in lines[i + 1]:
            buf = []
            while i < n and lines[i].strip().startswith("|"):
                buf.append(lines[i].strip())
                i += 1
            emit_table(buf)
            continue

        if s.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].lstrip())
                i += 1
            emit_callout(buf)
            continue

        im = _IMG.match(s)
        if im:
            emit_image(im.group(1), im.group(2))
            i += 1
            continue

        m = _H.match(s)
        if m:
            level = len(m.group(1))
            text, _ = split_heading(m.group(2).strip())
            emit_heading(level, text, anchors.get(text))
            i += 1
            continue

        bm = _BULLET.match(raw)
        if bm:
            emit_bullet(bm.group(2), level=1 if len(bm.group(1)) >= 2 else 0)
            i += 1
            continue

        nm = _NUM.match(raw)
        if nm:
            emit_numbered(nm.group(2), nm.group(3))
            i += 1
            continue

        if s == "":
            i += 1
            continue

        para = [s]
        i += 1
        while i < n and not is_block_start(lines[i].strip(), lines[i]):
            para.append(lines[i].strip())
            i += 1
        emit_paragraph(" ".join(para))


# Sections and their table of contents -----------------------------------------
def section_files(lang):
    return sorted((CONTENT_DIR / lang).glob("*.md"))


def toc_entries(lang):
    """[(level, title, anchor, file)] for every '# ' heading of a language."""
    entries = []
    for path in section_files(lang):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _H.match(line.strip())
            if not m or len(m.group(1)) > 1:
                continue
            title, anchor = split_heading(m.group(2).strip())
            if anchor is None:
                anchor = f"{lang}-{path.stem}-{len(entries)}"
            entries.append((len(m.group(1)), clean_heading(title), anchor, path))
    return entries


# Header and footer ------------------------------------------------------------
hp = section.header.paragraphs[0]
hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
add_internal_link(hp, "toc", "↑ Contents · Содержание", size=9)

fp = section.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
fp.add_run("AI Unit Test Assistant — PDP presentation     |     ")
fld = OxmlElement("w:fldSimple")
fld.set(qn("w:instr"), "PAGE \\* MERGEFORMAT")
r = OxmlElement("w:r")
t = OxmlElement("w:t")
t.text = "1"
r.append(t)
fld.append(r)
fp._p.append(fld)
for run in fp.runs:
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)


def back_to_toc(label):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(14)
    paragraph_border(p, ["top"], color="BFBFBF", size=6, space=6)
    add_internal_link(p, "toc", f"↩ {label}", bold=True)


def spacer(pts):
    doc.add_paragraph().paragraph_format.space_after = Pt(pts)


def centered(text, size, bold=False, italic=False, color=None, space_after=4):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(space_after)
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    if color is not None:
        r.font.color.rgb = color
    return p


# Title page -------------------------------------------------------------------
spacer(54)
centered("PERSONAL DEVELOPMENT PLAN", 12, bold=True, color=RGBColor(0x80, 0x80, 0x80))
spacer(10)
p = centered("PDP Presentation:", 30, bold=True, color=NAVY, space_after=0)
p.runs[0].add_break()
r2 = p.add_run("AI Unit Test Assistant")
r2.bold = True
r2.font.size = Pt(30)
r2.font.color.rgb = NAVY
rule = doc.add_paragraph()
rule.alignment = WD_ALIGN_PARAGRAPH.CENTER
paragraph_border(rule, ["bottom"], color="2E5496", size=18, space=1)
spacer(14)
centered(
    "How one small project covers eight PDP topics: AI productivity, CI/CD with coding agents, "
    "unit test automation, LLM development, distributed systems and cloud, monitoring, "
    "algorithms, and time management.",
    13, italic=True, color=RGBColor(0x40, 0x40, 0x40), space_after=10,
)
centered(
    "Как один небольшой проект покрывает восемь тем PDP: AI-продуктивность, CI/CD с coding agents, "
    "автоматизация unit-тестов, разработка с LLM, распределённые системы и облако, мониторинг, "
    "алгоритмы и тайм-менеджмент.",
    11, italic=True, color=RGBColor(0x60, 0x60, 0x60),
)
spacer(16)
centered("Part A — English  ·  Часть B — Русская версия", 11, color=RGBColor(0x70, 0x70, 0x70))
spacer(80)
for label, value in [("Author:", "Oleh Kokhan"), ("Date:", "15 October 2026"), ("Version:", "3.0")]:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4)
    rl = p.add_run(label + " ")
    rl.bold = True
    rl.font.size = Pt(12)
    rv = p.add_run(value)
    rv.font.size = Pt(12)
doc.add_page_break()


# Table of contents --------------------------------------------------------------
toc_title = doc.add_heading("Contents · Содержание", level=1)
add_bookmark(toc_title, "toc")
instr = doc.add_paragraph()
instr.paragraph_format.space_after = Pt(6)
ri = instr.add_run(
    "Click a line to jump to the section. Every page has a link back here in its header. "
    "Part A is the English version, Part B the Russian one; each part is complete on its own."
)
ri.italic = True
ri.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

for lang, part_title, _, _, _ in PARTS:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    add_internal_link(p, f"part-{lang}", part_title, bold=True, size=13, color="1F3864")
    for level, title, anchor, _ in toc_entries(lang):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent = Inches(0.25 if level == 1 else 0.6)
        add_internal_link(p, anchor, title, bold=(level == 1), size=11.5 if level == 1 else 10.5)
doc.add_page_break()


# Parts ----------------------------------------------------------------------------
for lang, part_title, _, _, back_label in PARTS:
    p = doc.add_heading(part_title, level=1)
    p.paragraph_format.page_break_before = True
    add_bookmark(p, f"part-{lang}")
    for path in section_files(lang):
        anchors = {title: anchor for _, title, anchor, src in toc_entries(lang) if src == path}
        p = doc.add_paragraph()
        p.paragraph_format.page_break_before = True
        p.paragraph_format.space_after = Pt(0)
        render_markdown(path.read_text(encoding="utf-8"), anchors)
        back_to_toc(back_label)

doc.save(OUT_PATH)
print("Saved:", OUT_PATH)
