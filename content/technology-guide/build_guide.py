"""Assemble the technology guide from the part files in this folder.

Outputs:
  PDP_Technology_Guide.html     bilingual page with a language toggle (the artifact)
  PDP_Technology_Guide.en.html  standalone English page
  PDP_Technology_Guide.ru.html  standalone Russian page
Run: python build_guide.py
"""

from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "PDP_Technology_Guide.html"

STYLE = (HERE / "style.css").read_text(encoding="utf-8")

SWITCH = """
(function () {
  var buttons = Array.prototype.slice.call(document.querySelectorAll('[data-lang]'));
  function show(lang) {
    ['en', 'ru'].forEach(function (l) { document.getElementById('lang-' + l).hidden = l !== lang; });
    buttons.forEach(function (b) { b.setAttribute('aria-selected', String(b.getAttribute('data-lang') === lang)); });
    document.documentElement.lang = lang;
    try { localStorage.setItem('pdp-guide-lang', lang); } catch (e) {}
  }
  buttons.forEach(function (b) { b.addEventListener('click', function () { show(b.getAttribute('data-lang')); window.scrollTo(0, 0); }); });
  var initial = 'en';
  if (location.hash.indexOf('#ru') === 0) { initial = 'ru'; }
  else if (location.hash.indexOf('#en') !== 0) { try { initial = localStorage.getItem('pdp-guide-lang') || 'en'; } catch (e) {} }
  show(initial === 'ru' ? 'ru' : 'en');
})();
"""

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600'
    '&family=Onest:wght@600;700&family=Source+Sans+3:wght@400;600;700&display=swap">\n'
)


def read_parts(lang):
    return "\n".join(f.read_text(encoding="utf-8") for f in sorted(HERE.glob(f"{lang}-part*.html"))) + "\n</article>"


def build():
    widgets = (HERE / "widgets.js").read_text(encoding="utf-8")
    en, ru = read_parts("en"), read_parts("ru")

    # Bilingual page with the language toggle (published as the artifact).
    page = (
        "<title>PDP Technology Guide</title>\n"
        + FONTS
        + f"<style>{STYLE}</style>\n"
        '<div class="topbar"><span class="brand">PDP Technology Guide</span>'
        '<div class="lang-switch" role="tablist" aria-label="Language">'
        '<button type="button" role="tab" data-lang="en" aria-selected="true">English</button>'
        '<button type="button" role="tab" data-lang="ru" aria-selected="false">Русский</button>'
        "</div></div>\n"
        f'<main class="page">\n{en}\n{ru}\n</main>\n'
        f"<script>{widgets}</script>\n<script>{SWITCH}</script>\n"
    )
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.name} ({len(page) // 1024} KB)")

    # One complete, standalone file per language: no toggle, nothing hidden, opens from disk.
    for lang, article, title in (("en", en, "PDP Technology Guide"), ("ru", ru, "PDP Technology Guide (RU)")):
        visible = article.replace(f'<article id="lang-{lang}" lang="{lang}" hidden>', f'<article id="lang-{lang}" lang="{lang}">')
        standalone = (
            f'<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{title}</title>\n"
            + FONTS
            + f"<style>{STYLE}\nbody{{margin:0}}[hidden]{{display:none!important}}</style>\n</head>\n<body>\n"
            f'<div class="topbar"><span class="brand">{title}</span></div>\n'
            f'<main class="page">\n{visible}\n</main>\n'
            f"<script>{widgets}</script>\n</body>\n</html>\n"
        )
        out = HERE / f"PDP_Technology_Guide.{lang}.html"
        out.write_text(standalone, encoding="utf-8")
        print(f"wrote {out.name} ({len(standalone) // 1024} KB)")


if __name__ == "__main__":
    build()
