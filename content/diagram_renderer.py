"""Three-column flow diagrams in the style of the user's release-pipeline picture."""

from html import escape

VIEW_W = 960
COL_X = (24, 332, 664)
COL_W = (272, 296, 272)
BOX_H = 78
PITCH = 112
TOP = 76
HEAD_Y = 44
TONES = ("a", "b", "c")


def _text_width(text, size, bold):
    width = 0.0
    for ch in text:
        if ch in " .,:;|·/()[]{}'`!":
            factor = 0.3
        elif "Ѐ" <= ch <= "ӿ":
            factor = 0.66 if ch.isupper() else 0.56
        elif ch.isupper():
            factor = 0.62
        elif ch.isdigit():
            factor = 0.53
        elif ch in "mwMW→":
            factor = 0.82
        elif ch in "iljtfr":
            factor = 0.3
        else:
            factor = 0.52
        width += factor * size
    return width * (1.06 if bold else 1.0)


def _check_fit(label, text, size, bold, box_w, warnings):
    limit = box_w - 22
    width = _text_width(text, size, bold)
    if width > limit:
        warnings.append(f"{label}: '{text}' ~{width:.0f}px > {limit}px")


def render(spec, lang, warnings):
    rows = spec["rows"]
    seq_col = spec.get("seq_col")
    footer = spec.get("footer", {}).get(lang)
    uid = f"{spec['id']}-{lang}"
    last_box_bottom = TOP + (len(rows) - 1) * PITCH + BOX_H
    height = last_box_bottom + (56 if footer else 28)

    parts = [
        f'<svg class="dg" viewBox="0 0 {VIEW_W} {height}" role="img" '
        f'aria-label="{escape(spec["caption"][lang])}" xmlns="http://www.w3.org/2000/svg">',
        "<defs>",
        f'<marker id="ah-{uid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path class="dg-arrowhead" d="M0,0 L10,5 L0,10 z"/></marker>',
        "</defs>",
    ]

    for col, header in enumerate(spec["columns"]):
        cx = COL_X[col] + COL_W[col] / 2
        parts.append(
            f'<text class="dg-head" x="{cx:.0f}" y="{HEAD_Y}" text-anchor="middle">'
            f"{escape(header[lang])}</text>"
        )

    for index, row in enumerate(rows):
        y = TOP + index * PITCH
        for col in range(3):
            cell = row[col]
            dashed = row.get("dashed") == col
            tone = "d" if dashed else TONES[col]
            x, w = COL_X[col], COL_W[col]
            title, sub = cell[0][lang], cell[1][lang]
            _check_fit(f"{spec['id']}/{lang} r{index} c{col} title", title, 17, True, w, warnings)
            _check_fit(f"{spec['id']}/{lang} r{index} c{col} sub", sub, 14, False, w, warnings)
            dash_attr = ' stroke-dasharray="6 5"' if dashed else ""
            parts.append(
                f'<rect class="dg-box dg-{tone}" x="{x}" y="{y}" width="{w}" height="{BOX_H}" '
                f'rx="10"{dash_attr}/>'
            )
            cx = x + w / 2
            parts.append(
                f'<text class="dg-title dg-{tone}-t" x="{cx:.0f}" y="{y + 33}" text-anchor="middle">'
                f"{escape(title)}</text>"
            )
            parts.append(
                f'<text class="dg-sub dg-{tone}-s" x="{cx:.0f}" y="{y + 57}" text-anchor="middle">'
                f"{escape(sub)}</text>"
            )
        mid_y = y + BOX_H / 2
        for col in range(2):
            x1 = COL_X[col] + COL_W[col] + 3
            x2 = COL_X[col + 1] - 4
            parts.append(
                f'<line class="dg-line" x1="{x1}" y1="{mid_y:.0f}" x2="{x2}" y2="{mid_y:.0f}" '
                f'marker-end="url(#ah-{uid})"/>'
            )
        if seq_col is not None and index > 0 and row.get("link", True):
            cx = COL_X[seq_col] + COL_W[seq_col] / 2
            y1 = y - PITCH + BOX_H + 3
            y2 = y - 4
            parts.append(
                f'<line class="dg-line" x1="{cx:.0f}" y1="{y1}" x2="{cx:.0f}" y2="{y2}" '
                f'marker-end="url(#ah-{uid})"/>'
            )

    if footer:
        parts.append(
            f'<text class="dg-foot" x="{VIEW_W / 2:.0f}" y="{height - 20}" text-anchor="middle">'
            f"{escape(footer)}</text>"
        )
    parts.append("</svg>")
    svg = "".join(parts)
    return (
        f'<figure class="diagram" id="{uid}"><div class="dg-scroll">{svg}</div>'
        f"<figcaption>{escape(spec['caption'][lang])}</figcaption></figure>"
    )
