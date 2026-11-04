#!/usr/bin/env python3
"""칼럼 빌드 스크립트 (표준 라이브러리만 사용).

content/columns/*.md  →  column/<slug>/index.html
                      →  column/index.html (목록)
                      →  index.html 의 <!--COLUMNS:START--> ~ <!--COLUMNS:END--> 사이 (최신 3편)
                      →  sitemap.xml

사용법:  python3 tools/build.py
설정:    tools/site.json
"""
import html
import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo


def today_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "tools", "site.json"), encoding="utf-8"))
URL = CFG["url"].rstrip("/")


def tpl(name):
    return open(os.path.join(ROOT, "templates", name), encoding="utf-8").read()


def fill(t, d):
    for k, v in d.items():
        t = t.replace("{{" + k + "}}", v)
    return t


def esc(s):
    return html.escape(s, quote=True)


def inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+|/[^)\s]*)\)",
        lambda m: '<a href="%s"%s>%s</a>'
        % (m.group(2), ' target="_blank" rel="noopener"' if m.group(2).startswith("http") else "", m.group(1)),
        s,
    )
    return s


def md_to_html(md):
    lines = md.strip("\n").split("\n")
    out, i = [], 0
    toc = []
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        if ln.startswith("## "):
            t = ln[3:].strip()
            hid = "s%d" % (len(toc) + 1)
            toc.append((hid, t))
            out.append('<h2 id="%s">%s</h2>' % (hid, inline(t)))
            i += 1
            continue
        if ln.startswith("### "):
            out.append("<h3>%s</h3>" % inline(ln[4:].strip()))
            i += 1
            continue
        if ln.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].startswith("> "):
                buf.append(lines[i][2:])
                i += 1
            out.append('<blockquote><p>%s</p></blockquote>' % "<br>".join(inline(b) for b in buf))
            continue
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            h = "<tr>%s</tr>" % "".join("<th>%s</th>" % inline(c) for c in rows[0])
            b = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r) for r in rows[1:])
            out.append('<div class="tbl"><table><thead>%s</thead><tbody>%s</tbody></table></div>' % (h, b))
            continue
        if re.match(r"^- ", ln):
            buf = []
            while i < len(lines) and lines[i].startswith("- "):
                buf.append(lines[i][2:])
                i += 1
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline(b) for b in buf))
            continue
        if re.match(r"^\d+\. ", ln):
            buf = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                buf.append(re.sub(r"^\d+\. ", "", lines[i]))
                i += 1
            out.append("<ol>%s</ol>" % "".join("<li>%s</li>" % inline(b) for b in buf))
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{2,3} |> |\||- |\d+\. )", lines[i]):
            buf.append(lines[i])
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(buf)))
    return "\n".join(out), toc


def parse(path):
    raw = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        sys.exit("front matter 없음: " + path)
    meta, sources, key = {}, [], None
    for ln in m.group(1).split("\n"):
        if ln.startswith("  - ") and key == "sources":
            sources.append(ln[4:].strip())
        elif ":" in ln:
            key, v = ln.split(":", 1)
            key = key.strip()
            meta[key] = v.strip()
    meta["sources"] = sources
    for k in ("title", "description", "date", "slug", "category"):
        if not meta.get(k):
            sys.exit("%s 에 %s 가 없습니다" % (path, k))
    if not re.fullmatch(r"[a-z0-9-]+", meta["slug"]):
        sys.exit("slug 는 영문 소문자, 숫자, - 만: " + path)
    meta["body"] = m.group(2)
    return meta


def date_ko(d):
    y, mo, da = d.split("-")
    return "%s년 %d월 %d일" % (y, int(mo), int(da))


def main():
    cdir = os.path.join(ROOT, "content", "columns")
    posts = [parse(os.path.join(cdir, f)) for f in sorted(os.listdir(cdir)) if f.endswith(".md")]
    posts = [p for p in posts if p["date"] <= today_kst()]
    posts.sort(key=lambda p: p["date"], reverse=True)
    slugs = [p["slug"] for p in posts]
    if len(slugs) != len(set(slugs)):
        sys.exit("slug 중복")

    t_col, t_item, t_list, t_home = tpl("column.html"), tpl("list-item.html"), tpl("list.html"), tpl("home-item.html")

    def item(t, p):
        return fill(t, {
            "HREF": "/column/%s/" % p["slug"],
            "TITLE": esc(p["title"]),
            "DESCRIPTION": esc(p["description"]),
            "DATE": p["date"],
            "DATE_KO": date_ko(p["date"]),
            "CATEGORY": esc(p["category"]),
        })

    for idx, p in enumerate(posts):
        body, toc = md_to_html(p["body"])
        src = ""
        if p["sources"]:
            lis = []
            for s in p["sources"]:
                if " | " in s:
                    label, link = s.rsplit(" | ", 1)
                    lis.append('<li><a href="%s" target="_blank" rel="noopener">%s</a></li>' % (esc(link), esc(label)))
                else:
                    lis.append("<li>%s</li>" % esc(s))
            src = '<section class="sources"><h2>참고 자료</h2><ul>%s</ul></section>' % "".join(lis)
        others = [q for q in posts if q is not p][:3]
        related = "".join(item(t_item, q) for q in others)
        url = "%s/column/%s/" % (URL, p["slug"])
        ld = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": p["title"],
            "description": p["description"],
            "datePublished": p["date"],
            "dateModified": p.get("updated") or p["date"],
            "author": {"@type": "Organization", "name": CFG["name"], "url": URL + "/"},
            "publisher": {"@type": "Organization", "name": CFG["name"], "logo": {"@type": "ImageObject", "url": URL + "/" + CFG["logo"]}},
            "mainEntityOfPage": url,
            "image": URL + "/" + CFG["og_image"],
            "inLanguage": "ko-KR",
        }
        toc_html = "".join('<li><a href="#%s">%s</a></li>' % (h, esc(re.sub(r"^\d+\.\s*", "", t))) for h, t in toc)
        page = fill(t_col, {
            "TITLE": esc(p["title"]),
            "DESCRIPTION": esc(p["description"]),
            "KEYWORDS": esc(p.get("keywords", "")),
            "URL": url,
            "OG_IMAGE": URL + "/" + CFG["og_image"],
            "DATE": p["date"],
            "DATE_KO": date_ko(p["date"]),
            "CATEGORY": esc(p["category"]),
            "TOC": toc_html,
            "BODY": body,
            "SOURCES": src,
            "RELATED_SECTION": ('<section class="wrap related"><h2>다른 칼럼</h2><div class="items">%s</div></section>' % related) if related else "",
            "JSONLD": json.dumps(ld, ensure_ascii=False),
        })
        od = os.path.join(ROOT, "column", p["slug"])
        os.makedirs(od, exist_ok=True)
        open(os.path.join(od, "index.html"), "w", encoding="utf-8").write(page)

    # 지워진 칼럼의 폴더 정리
    coldir = os.path.join(ROOT, "column")
    os.makedirs(coldir, exist_ok=True)
    for d in os.listdir(coldir):
        full = os.path.join(coldir, d)
        if os.path.isdir(full) and d not in slugs:
            for f in os.listdir(full):
                os.remove(os.path.join(full, f))
            os.rmdir(full)

    lst = fill(t_list, {
        "ITEMS": "".join(item(t_item, p) for p in posts),
        "URL": URL + "/column/",
        "OG_IMAGE": URL + "/" + CFG["og_image"],
        "COUNT": str(len(posts)),
    })
    open(os.path.join(coldir, "index.html"), "w", encoding="utf-8").write(lst)

    ip = os.path.join(ROOT, "index.html")
    s = open(ip, encoding="utf-8").read()
    a, b = "<!--COLUMNS:START-->", "<!--COLUMNS:END-->"
    if a in s and b in s:
        block = "".join(item(t_home, p) for p in posts[:3])
        s = s[: s.index(a) + len(a)] + "\n" + block + "\n" + s[s.index(b):]
        open(ip, "w", encoding="utf-8").write(s)

    today = today_kst()
    urls = [(URL + "/", posts[0]["date"] if posts else today, "1.0"), (URL + "/column/", posts[0]["date"] if posts else today, "0.8")]
    urls += [("%s/column/%s/" % (URL, p["slug"]), p.get("updated") or p["date"], "0.7") for p in posts]
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sm += "".join("  <url><loc>%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>\n" % u for u in urls)
    sm += "</urlset>\n"
    open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8").write(sm)
    print("칼럼 %d편 빌드 완료" % len(posts))


if __name__ == "__main__":
    main()
