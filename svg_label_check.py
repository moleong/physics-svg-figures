#!/usr/bin/env python3
"""svg_label_check.py — SVG 講義插圖「文字標註 × 線段碰撞」量測工具
（physics-svg-figures skill 附帶；交付前必跑）

用法：
    python3 svg_label_check.py 講義.html [更多檔案...] [--threshold 6]
    python3 svg_label_check.py 圖.svg

輸入為 HTML 時自動抽出所有 <svg class="diagram"> 區塊逐圖檢查。
對每個 <text> 估算墨區（依 text-anchor、font-size、字元寬度表），
量測到圖中所有筆畫（line/polyline/polygon/rect/circle/ellipse/path 取樣）
的最近距離；marker-end 箭頭沿線延伸 8px 計入。

低於 --threshold（預設 6px）者列為 flag，結束時 exit code = 1。
刻意重疊（支點圓內的 O、矢號箭頭貼字母上方等）請在原始碼以
data-check="ignore" 聲明：加在 <text> 上跳過該標籤，加在圖元上跳過該筆畫。
支援 translate/scale/rotate(含中心)/matrix 巢狀 transform（世界座標量測）；
自動略過 defs/marker/pattern 定義；文字寬度為估算值且假設文字未隨群組旋轉
（本系列電路圖皆如此），邊界個案以渲染目視為準。

建議工作流程（修復 flag 時）：
第一輪就對全部 flag 列印「真實墨盒＋最近線段」——import 本模組後用
text_ink_rect() 取每個 <text> 的估算墨區，用 seg_rect_dist() 找最近筆畫，
一次性批量求解。手算盒寬／anchor 屢屢與工具盒不符（已多次推翻「手算已清」，
首輪猜測命中率約五成）。注意 text-anchor：無此屬性 = start，盒從 x 向右
延伸；middle 才是以 x 居中。另附 rect_line_distances()（驗旋轉物塊貼線、
底面中點垂距 ≈0）與 seg_seg_dist()（驗兩線段淨空，相交 = 0）。
"""
import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET

MARKER_EXT = 8.0  # marker-end 箭頭尖端超出線段端點的近似距離

# 字元寬度（em 為單位，依 Times/Helvetica 混合估算，偏保守）
CHAR_W = [
    (re.compile(r'[\u2e80-\u9fff\uff00-\uffef]'), 1.0),   # CJK 全形
    (re.compile(r'[A-Z]'), 0.62),
    (re.compile(r'[0-9]'), 0.56),
    (re.compile(r'[°]'), 0.45),
    (re.compile(r'[×·]'), 0.55),
    (re.compile(r'[θ⊥∥]'), 0.55),
    (re.compile(r'[-−]'), 0.40),
    (re.compile(r'\s'), 0.30),
]
CHAR_W_DEFAULT = 0.50
DESCENDERS = set('gjpqy')


def char_w(ch):
    for pat, w in CHAR_W:
        if pat.match(ch):
            return w
    return CHAR_W_DEFAULT


def strip_ns(tag):
    return tag.rsplit('}', 1)[-1]


def tokenize_d(d):
    return re.findall(r'[MmLlHhVvAaQqCcZz]|-?\d*\.?\d+(?:e[-+]?\d+)?', d)


def arc_points(p0, rx, ry, rot, large, sweep, p1, steps=24):
    """橢圓弧取樣為折線（SVG endpoint parametrization）。"""
    if rx == 0 or ry == 0:
        return [p0, p1]
    phi = math.radians(rot)
    cosp, sinp = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1p = cosp * dx + sinp * dy
    y1p = -sinp * dx + cosp * dy
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    sgn = -1 if large == sweep else 1
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = sgn * math.sqrt(max(0.0, num / den)) if den else 0.0
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cosp * cxp - sinp * cyp + (p0[0] + p1[0]) / 2
    cy = sinp * cxp + cosp * cyp + (p0[1] + p1[1]) / 2
    a1 = math.atan2((p0[1] - cy) / ry, (p0[0] - cx) / rx)
    a2 = math.atan2((p1[1] - cy) / ry, (p1[0] - cx) / rx)
    if sweep == 1 and a2 < a1:
        a2 += 2 * math.pi
    if sweep == 0 and a2 > a1:
        a2 -= 2 * math.pi
    pts = []
    for k in range(1, steps + 1):
        a = a1 + (a2 - a1) * k / steps
        x = cx + rx * math.cos(a) * cosp - ry * math.sin(a) * sinp
        y = cy + rx * math.cos(a) * sinp + ry * math.sin(a) * cosp
        pts.append((x, y))
    return pts


def path_segments(d):
    t = tokenize_d(d)
    segs, sub = [], []          # sub = 目前子路徑的取樣點列
    i, cur, start = 0, (0.0, 0.0), (0.0, 0.0)

    def num():
        nonlocal i
        v = float(t[i]); i += 1
        return v

    def emit(pts):
        nonlocal sub
        if not sub:
            sub = [pts[0]]
        sub.extend(pts[1:])

    while i < len(t):
        cmd = t[i]; i += 1
        rel = cmd.islower()
        c = cmd.upper()
        need = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'A': 7, 'Q': 4, 'C': 6}.get(c, 0)
        if i + need > len(t):   # 殘缺路徑資料，截斷而非崩潰
            break
        if c == 'M':
            x, y = num(), num()
            cur = (cur[0] + x, cur[1] + y) if rel else (x, y)
            if sub:
                segs.append(sub)
            sub, start = [cur], cur
        elif c == 'L':
            x, y = num(), num()
            p = (cur[0] + x, cur[1] + y) if rel else (x, y)
            emit([cur, p]); cur = p
        elif c == 'H':
            x = num()
            p = (cur[0] + x, cur[1]) if rel else (x, cur[1])
            emit([cur, p]); cur = p
        elif c == 'V':
            y = num()
            p = (cur[0], cur[1] + y) if rel else (cur[0], y)
            emit([cur, p]); cur = p
        elif c == 'A':
            rx, ry, rot, large, sweep = num(), num(), num(), int(num()), int(num())
            x, y = num(), num()
            p = (cur[0] + x, cur[1] + y) if rel else (x, y)
            emit(arc_points(cur, rx, ry, rot, large, sweep, p)); cur = p
        elif c in ('Q', 'C'):
            n = 3 if c == 'C' else 2   # C=三控制點(6 數)、Q=控制點+終點(4 數)
            vals = [num() for _ in range(2 * n)]
            pts = [(cur[0] + vals[j], cur[1] + vals[j + 1]) if rel else (vals[j], vals[j + 1])
                   for j in range(0, 2 * n, 2)]
            p_end = pts[-1]
            ctrl = [cur] + pts[:-1]
            samples = []
            for k in range(1, 17):
                u = k / 16
                ps = ctrl[:]
                while len(ps) > 1:
                    ps = [((1 - u) * a[0] + u * b[0], (1 - u) * a[1] + u * b[1])
                          for a, b in zip(ps, ps[1:])]
                samples.append(ps[0])
            emit([cur] + samples); cur = p_end
        elif c == 'Z':
            emit([cur, start]); cur = start
    if sub:
        segs.append(sub)
    out = []
    for pts in segs:
        out.extend(zip(pts, pts[1:]))
    return out


def seg_rect_dist(p1, p2, rect):
    x0, y0 = p1; x1, y1 = p2
    length = math.hypot(x1 - x0, y1 - y0)
    n = max(2, int(length))
    rx0, ry0, rx1, ry1 = rect
    best = math.inf
    for k in range(n + 1):
        u = k / n
        px, py = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
        dx = max(rx0 - px, 0.0, px - rx1)
        dy = max(ry0 - py, 0.0, py - ry1)
        best = min(best, math.hypot(dx, dy))
    return best


def _pt_seg_dist(p, a, b):
    ax, ay = a; bx, by = b
    L2 = (bx - ax) ** 2 + (by - ay) ** 2
    if L2 == 0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / L2))
    return math.hypot(p[0] - (ax + t * (bx - ax)), p[1] - (ay + t * (by - ay)))


def _ori(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def seg_seg_dist(p1, p2, q1, q2):
    """兩線段最近距離（相交 = 0）。驗算繩／擋板／箭頭／彈簧對斜面、地面的全長淨空：
    畫完線段類元素後必跑，淨空應 ≥ 設計間隙（貼合類元素除外，其距離應 ≈ 0）。"""
    d1, d2 = _ori(p1, p2, q1), _ori(p1, p2, q2)
    d3, d4 = _ori(q1, q2, p1), _ori(q1, q2, p2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 != 0 and d2 != 0 and d3 != 0 and d4 != 0:
        return 0.0
    for p in (p1, p2):
        if min(_ori(q1, q2, p), 0) * max(_ori(q1, q2, p), 0) == 0 and _pt_seg_dist(p, q1, q2) < 1e-9:
            return 0.0
    return min(_pt_seg_dist(p1, q1, q2), _pt_seg_dist(p2, q1, q2),
               _pt_seg_dist(q1, p1, p2), _pt_seg_dist(q2, p1, p2))


def rect_line_distances(x, y, w, h, rot_deg, cx, cy, p1, p2):
    """驗算旋轉矩形與直線的貼合關係（放物塊於斜面/桌面後必驗）。

    回傳四角與四邊中點到直線的帶號垂直距離（線方向為 p1→p2，左側為正）。
    貼合判準（以底面貼斜面為例）：底邊中點 |d| < 1.0，且底面兩角同號、
    |d| < 1.5（無一角沉入線下）。正數在線左側（沿 p1→p2 方向的左手邊）。
    """
    m = parse_transform(f'rotate({rot_deg} {cx} {cy})')
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    L = math.hypot(dx, dy) or 1.0
    ux, uy = -dy / L, dx / L          # 左側法線

    def sd(px, py):
        q = apply_mat(m, (px, py))
        return (q[0] - p1[0]) * ux + (q[1] - p1[1]) * uy

    pts = {
        'TL': (x, y), 'TR': (x + w, y), 'BR': (x + w, y + h), 'BL': (x, y + h),
        'top_mid': (x + w / 2, y), 'right_mid': (x + w, y + h / 2),
        'bottom_mid': (x + w / 2, y + h), 'left_mid': (x, y + h / 2),
    }
    return {k: round(sd(*v), 2) for k, v in pts.items()}


def mat_mul(m1, m2):
    """2×3 仿射矩陣合成：m1 ∘ m2（先 m2 後 m1）。"""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def parse_transform(s):
    """支援 translate / scale / rotate(含旋轉中心) / matrix。無法解析的片段忽略。"""
    m = (1, 0, 0, 1, 0, 0)
    for name, args in re.findall(r'(translate|scale|rotate|matrix)\s*\(([^)]*)\)', s):
        v = [float(x) for x in re.split(r'[\s,]+', args.strip()) if x]
        if name == 'translate' and len(v) >= 1:
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == 'scale' and len(v) >= 1:
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == 'rotate' and len(v) >= 1:
            rad = math.radians(v[0])
            cos, sin = math.cos(rad), math.sin(rad)
            r = (cos, sin, -sin, cos, 0, 0)
            if len(v) >= 3:  # rotate(deg, cx, cy) = 平移(cx,cy) ∘ 旋轉 ∘ 平移(-cx,-cy)
                t = mat_mul((1, 0, 0, 1, v[1], v[2]), mat_mul(r, (1, 0, 0, 1, -v[1], -v[2])))
            else:
                t = r
        elif name == 'matrix' and len(v) >= 6:
            t = tuple(v[:6])
        else:
            continue
        m = mat_mul(m, t)
    return m


def apply_mat(m, p):
    a, b, c, d, e, f = m
    return (a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f)


def apply_dir(m, p):
    """方向向量：只取線性部分（不平移）。"""
    a, b, c, d, _, _ = m
    return (a * p[0] + c * p[1], b * p[0] + d * p[1])


def collect_segments(root):
    """回傳 (segments, ignored_count)；全程在世界座標系量測（含 transform 巢狀合成）。"""
    segs = []
    ignored = 0

    def walk(el, parent_m):
        nonlocal ignored
        m = mat_mul(parent_m, parse_transform(el.get('transform', '')))
        tag = strip_ns(el.tag)
        if el.get('data-check') == 'ignore' or tag in ('defs', 'marker', 'pattern', 'clipPath', 'mask', 'symbol'):
            ignored += 1
            return  # 子樹一併略過（defs 內是 marker/pattern 定義，非渲染筆畫）

        def T(p):
            return apply_mat(m, p)

        def D(p):
            return apply_dir(m, p)

        def add_poly(pts, marker_end):
            wpts = [T(p) for p in pts]
            for a, b in zip(wpts, wpts[1:]):
                segs.append((a, b))
            if marker_end and len(wpts) >= 2:
                d = (wpts[-1][0] - wpts[-2][0], wpts[-1][1] - wpts[-2][1])
                L = math.hypot(*d) or 1.0
                tip = (wpts[-1][0] + d[0] / L * MARKER_EXT, wpts[-1][1] + d[1] / L * MARKER_EXT)
                segs.append((wpts[-1], tip))

        try:
            if tag == 'line':
                add_poly([(float(el.get('x1', 0)), float(el.get('y1', 0))),
                          (float(el.get('x2', 0)), float(el.get('y2', 0)))], el.get('marker-end'))
            elif tag in ('polyline', 'polygon'):
                nums = [float(v) for v in re.split(r'[\s,]+', el.get('points', '').strip()) if v]
                pts = list(zip(nums[::2], nums[1::2]))
                if tag == 'polygon' and pts:
                    pts.append(pts[0])
                add_poly(pts, el.get('marker-end'))
            elif tag == 'rect':
                x, y = float(el.get('x', 0)), float(el.get('y', 0))
                w, h = float(el.get('width', 0)), float(el.get('height', 0))
                add_poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)], el.get('marker-end'))
            elif tag in ('circle', 'ellipse'):
                cx, cy = float(el.get('cx', 0)), float(el.get('cy', 0))
                if tag == 'circle':
                    rx = ry = float(el.get('r', 0))
                else:
                    rx, ry = float(el.get('rx', 0)), float(el.get('ry', 0))
                pts = [(cx + rx * math.cos(2 * math.pi * k / 72),
                        cy + ry * math.sin(2 * math.pi * k / 72)) for k in range(73)]
                add_poly(pts, el.get('marker-end'))
            elif tag == 'path':
                ps = path_segments(el.get('d', ''))
                if ps:
                    wps = [(T(a), T(b)) for a, b in ps]
                    if el.get('marker-end'):
                        a, b = wps[-1]
                        d = (b[0] - a[0], b[1] - a[1])
                        L = math.hypot(*d) or 1.0
                        wps.append((b, (b[0] + d[0] / L * MARKER_EXT, b[1] + d[1] / L * MARKER_EXT)))
                    segs.extend(wps)
        except (TypeError, ValueError, IndexError):
            print(f'  ⚠️  <{tag}> 屬性解析失敗，已略過', file=sys.stderr)

        for child in el:
            walk(child, m)

    walk(root, (1, 0, 0, 1, 0, 0))
    return segs, ignored


def text_ink_rect(el):
    content = ''.join(el.itertext())
    if not content.strip():
        return None
    fs = float(re.match(r'[\d.]+', el.get('font-size', '14')).group())
    x, y = float(el.get('x', 0)), float(el.get('y', 0))
    w = sum(char_w(ch) for ch in content) * fs
    anchor = el.get('text-anchor', 'start')
    if anchor == 'middle':
        x0, x1 = x - w / 2, x + w / 2
    elif anchor == 'end':
        x0, x1 = x - w, x
    else:
        x0, x1 = x, x + w
    has_desc = any(ch in DESCENDERS for ch in content)
    top = y - 0.72 * fs
    bot = y + (0.24 * fs if has_desc else 0.08 * fs)
    return (x0, top, x1, bot), content.strip()


def check_svg(svg_src, name, threshold, verbose):
    root = ET.fromstring(svg_src)
    view = root.get('viewBox')
    vb = [float(v) for v in view.split()] if view else None
    segs, ignored = collect_segments(root)
    flags, checked = [], 0
    for el in root.iter():
        if strip_ns(el.tag) != 'text' or el.get('data-check') == 'ignore':
            continue
        got = text_ink_rect(el)
        if not got:
            continue
        rect, content = got
        checked += 1
        d = min((seg_rect_dist(a, b, rect) for a, b in segs), default=math.inf)
        if vb:
            x0, y0, x1, y1 = rect
            if x0 < vb[0] - 1 or y0 < vb[1] - 1 or x1 > vb[0] + vb[2] + 1 or y1 > vb[1] + vb[3] + 1:
                flags.append((content, el.get('x'), el.get('y'), d, '超出 viewBox'))
                continue
        if d < threshold:
            flags.append((content, el.get('x'), el.get('y'), d, ''))
        elif verbose:
            print(f"    ok '{content}' @({el.get('x')},{el.get('y')}) {d:.1f}px")
    print(f'\n== {name} ==')
    print(f'  標籤 {checked} 個，筆畫 {len(segs)} 段' +
          (f'，已聲明忽略 {ignored} 個圖元' if ignored else ''))
    for content, x, y, d, note in flags:
        print(f"  ✗ '{content}' @({x},{y}) 距線段 {d:.1f}px < {threshold}px {note}".rstrip())
    return len(flags)


def extract_svgs(src):
    """以標籤平衡掃描抽出所有 <svg> 區塊（正則 <svg.*?</svg> 無法處理巢狀／不閉合標籤）。
    回傳 [(起始位置, svg 原始碼)]。"""
    blocks = []
    stack = []
    for m in re.finditer(r'<svg\b[^>]*>|</svg\s*>', src, re.I):
        if m.group(0).lstrip('<').rstrip('>').strip().startswith('/'):
            if stack:
                start = stack.pop()
                if not stack:  # 最外層閉合 → 一個完整區塊
                    blocks.append((start, src[start:m.end()]))
        else:
            stack.append(m.start())
    for start in stack:  # 未閉合的殘塊（HTML 容錯場景），截到檔尾
        blocks.append((start, src[start:]))
    blocks.sort()
    return blocks


def main():
    ap = argparse.ArgumentParser(description='SVG 講義插圖文字標註碰撞檢查')
    ap.add_argument('files', nargs='+')
    ap.add_argument('--threshold', type=float, default=6.0)
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    total = 0
    for path in args.files:
        src = open(path, encoding='utf-8').read()
        ms = extract_svgs(src)
        use_diagram_class = any('class="diagram"' in b[1][:200] for b in ms)
        if use_diagram_class:
            ms = [b for b in ms if 'class="diagram"' in b[1][:200]]
        blocks = [b[1] for b in ms] or [src]
        # 找每個 svg 前最近的 h1/h2 標題，方便對照
        headings = []
        pos = 0
        for start, _ in ms:
            h = None
            for hm in re.finditer(r'<h[12][^>]*>(.*?)</h[12]>', src[pos:start], re.S):
                txt = re.sub(r'<[^>]+>', '', hm.group(1)).strip()
                if txt:
                    h = txt
            headings.append(h or '?')
            pos = start
        if not ms:
            headings = [path]
        print(f'### {path}（{len(blocks)} 幅圖）')
        for idx, blk in enumerate(blocks):
            name = headings[idx] if idx < len(headings) else f'圖 {idx + 1}'
            try:
                total += check_svg(blk, name, args.threshold, args.verbose)
            except ET.ParseError as e:
                print(f'\n== {name} ==\n  ✗ SVG 解析失敗：{e}')
                total += 1
    print()
    if total:
        print(f'共 {total} 個 flag（< {args.threshold}px）。修正，或在原始碼以 data-check="ignore" 聲明刻意重疊。')
        sys.exit(1)
    print(f'全部通過（threshold {args.threshold}px）。')


if __name__ == '__main__':
    main()
