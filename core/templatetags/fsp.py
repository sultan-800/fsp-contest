import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


# --------------------------------------------------------------- безопасная разметка
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_ITAL = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\w)")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")


def _inline(s):
    # s уже экранирована
    codes = []

    def keep(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    s = _INLINE_CODE.sub(keep, s)
    s = _BOLD.sub(r"<strong>\1</strong>", s)
    s = _ITAL.sub(r"<em>\1</em>", s)
    s = _LINK.sub(r'<a href="\2" target="_blank" rel="noopener noreferrer nofollow">\1</a>', s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", s)
    return s


@register.filter(is_safe=True)
def markup(text):
    """Мини-markdown: всё содержимое экранируется ДО преобразования — XSS невозможен."""
    if not text:
        return ""
    text = escape(str(text)).replace("\r\n", "\n")
    out, para, lst, code, in_code = [], [], None, [], False

    def flush_para():
        if para:
            out.append("<p>" + "<br>".join(_inline(x) for x in para) + "</p>")
            para.clear()

    def flush_list():
        nonlocal lst
        if lst:
            tag, items = lst
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + f"</{tag}>")
            lst = None

    for line in text.split("\n"):
        if line.strip().startswith("```"):
            if in_code:
                out.append("<pre class=\"code-block\"><code>" + "\n".join(code) + "</code></pre>")
                code, in_code = [], False
            else:
                flush_para(); flush_list(); in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        st = line.strip()
        if not st:
            flush_para(); flush_list(); continue
        m = re.match(r"^(#{1,4})\s+(.*)$", st)
        if m:
            flush_para(); flush_list()
            lvl = min(4, len(m.group(1)) + 1)
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            continue
        m = re.match(r"^[-*•]\s+(.*)$", st)
        n = re.match(r"^\d+[.)]\s+(.*)$", st)
        if m or n:
            flush_para()
            tag = "ul" if m else "ol"
            if not lst or lst[0] != tag:
                flush_list(); lst = (tag, [])
            lst[1].append((m or n).group(1))
            continue
        if st.startswith("&gt;"):
            flush_para(); flush_list()
            out.append(f"<blockquote>{_inline(st[4:].strip())}</blockquote>")
            continue
        flush_list()
        para.append(st)
    if in_code:
        out.append("<pre class=\"code-block\"><code>" + "\n".join(code) + "</code></pre>")
    flush_para(); flush_list()
    return mark_safe("\n".join(out))


# --------------------------------------------------------------- утилиты
@register.filter
def get_item(d, key):
    try:
        return d.get(key)
    except AttributeError:
        return None


@register.filter
def plural(n, forms):
    """{{ n|plural:"задача,задачи,задач" }}"""
    try:
        n = abs(int(n))
    except (TypeError, ValueError):
        return forms.split(",")[-1]
    f = forms.split(",")
    if n % 10 == 1 and n % 100 != 11:
        return f[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f[1]
    return f[2]


@register.filter
def hm(minutes):
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return "—"
    return f"{minutes // 60}:{minutes % 60:02d}"


@register.filter
def pct(value, total):
    try:
        return int(round(float(value) / float(total) * 100)) if float(total) else 0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def fnum(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return v
    s = f"{v:,.1f}".replace(",", " ").replace(".", ",")
    return s[:-2] if s.endswith(",0") else s


@register.simple_tag(takes_context=True)
def qs(context, **kwargs):
    """Собирает querystring, сохраняя текущие параметры: {% qs page=2 %}"""
    q = context["request"].GET.copy()
    for k, v in kwargs.items():
        if v in (None, ""):
            q.pop(k, None)
        else:
            q[k] = v
    s = q.urlencode()
    return f"?{s}" if s else "?"


@register.simple_tag
def sparkline(points, width=560, height=140, pad=10):
    """SVG-график истории рейтинга (серверный рендер, без JS)."""
    vals = [float(p) for p in points]
    if not vals:
        return ""
    if len(vals) == 1:
        vals = [0.0] + vals
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    step = (width - pad * 2) / (len(vals) - 1)
    pts = [(pad + i * step, height - pad - (v - lo) / span * (height - pad * 2)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pad},{height - pad} " + line + f" {pts[-1][0]:.1f},{height - pad}"
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5"/>' for x, y in pts[1:])
    grid = "".join(f'<line x1="{pad}" x2="{width - pad}" y1="{pad + i * (height - 2 * pad) / 3:.1f}" '
                   f'y2="{pad + i * (height - 2 * pad) / 3:.1f}"/>' for i in range(4))
    svg = (f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img" '
           f'aria-label="История рейтинга">'
           f'<defs><linearGradient id="sg" x1="0" x2="0" y1="0" y2="1">'
           f'<stop offset="0" stop-color="currentColor" stop-opacity=".35"/>'
           f'<stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>'
           f'<g class="spark__grid">{grid}</g>'
           f'<polygon points="{area}" fill="url(#sg)"/>'
           f'<polyline points="{line}" fill="none" stroke="currentColor" stroke-width="2.5" '
           f'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
           f'<g class="spark__dots">{dots}</g></svg>')
    return mark_safe(svg)


@register.inclusion_tag("partials/status.html")
def status_badge(competition, size=""):
    return {"c": competition, "size": size}


@register.inclusion_tag("partials/avatar.html")
def avatar(user, size="md"):
    return {"u": user, "size": size}


@register.simple_tag
def icon(name, cls=""):
    return mark_safe(f'<svg class="i {escape(cls)}" aria-hidden="true"><use href="#i-{escape(name)}"></use></svg>')
