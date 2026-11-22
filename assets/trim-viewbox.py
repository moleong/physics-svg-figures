#!/usr/bin/env python3
"""以瀏覽器量測結果整理 class="diagram" 的 SVG viewBox。

  python3 trim-viewbox.py gen 講義.html -o /tmp/svg-harness.html
  python3 trim-viewbox.py apply bbox.txt 講義.html

getBBox() 主要回傳幾何邊界，不保證涵蓋所有 stroke／marker 外伸；因此加入
12 個 SVG 使用者單位的安全邊距，裁後仍須在實際宿主渲染複查。工具只改
viewBox，不改宿主的 width、max-width 或外距。刻意留白、多圖對齊或共同比例
的 SVG 加 data-viewbox="preserve" 後會完整略過。
"""
import argparse
import html
import math
import re


SVG_RE = re.compile(r'<svg\b[^>]*>.*?</svg>', re.S | re.I)
VB_RE = re.compile(r'view[Bb]ox\s*=\s*(["\'])(.*?)\1', re.S)
PAD = 12.0


def is_diagram(block):
    opening = re.match(r'<svg\b[^>]*>', block, re.S | re.I)
    if not opening:
        return False
    match = re.search(r'class\s*=\s*(["\'])(.*?)\1', opening.group(0), re.S)
    return bool(match and 'diagram' in match.group(2).split())


def is_preserved(block):
    opening = re.match(r'<svg\b[^>]*>', block, re.S | re.I)
    if not opening:
        return False
    match = re.search(r'data-viewbox\s*=\s*(["\'])(.*?)\1', opening.group(0), re.S | re.I)
    return bool(match and match.group(2).strip().lower() == 'preserve')


def parse_viewbox(block):
    match = VB_RE.search(block)
    if not match:
        return None, None
    try:
        values = [float(v) for v in re.split(r'[\s,]+', match.group(2).strip()) if v]
    except ValueError:
        return match, None
    if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
        return match, None
    return match, values


def fmt(value):
    return str(int(value)) if float(value).is_integer() else f'{value:.3f}'.rstrip('0').rstrip('.')


def diagram_matches(src):
    return [m for m in SVG_RE.finditer(src) if is_diagram(m.group(0))]


def collect(files):
    out = []
    for path in files:
        src = open(path, encoding='utf-8').read()
        blocks = [m.group(0) for m in diagram_matches(src)]
        if blocks:
            out.append((path, blocks))
    return out


def cmd_gen(files, out_path):
    parts = ['''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>svg measure</title></head>
<body>
<div id="stage" style="position:absolute;left:-99999px;top:0"></div>
<pre id="result"></pre>
''']
    total = 0
    for fi, (path, svgs) in enumerate(files):
        for si, svg in enumerate(svgs):
            match, _ = parse_viewbox(svg)
            vb_s = match.group(0) if match else 'viewBox="?"'
            name = html.escape(f'file{fi}|svg{si}|{path}|{vb_s}', quote=True)
            parts.append(f'<div class="fig" data-name="{name}">{svg}</div>\n')
            total += 1
    parts.append('''<script>
window.addEventListener('load', function () {
  var out = [];
  var stage = document.getElementById('stage');
  document.querySelectorAll('.fig').forEach(function (fig) {
    var svg = fig.querySelector('svg');
    stage.appendChild(svg);
    try {
      var bb = svg.getBBox();
      out.push(fig.dataset.name + ' ' + [bb.x, bb.y, bb.width, bb.height].map(function (v) { return v.toFixed(3); }).join(' '));
    } catch (e) {
      out.push(fig.dataset.name + ' ERROR ' + e.message);
    }
  });
  document.getElementById('result').textContent = out.join('\\n');
  document.body.dataset.ready = 'true';
});
</script></body></html>''')
    open(out_path, 'w', encoding='utf-8').write('\n'.join(parts))
    print(f'harness written: {out_path}（{total} 個 SVG，來自 {len(files)} 個檔案）')
    print('瀏覽器開啟後，等 body[data-ready="true"]，把 #result 全文存成 bbox.txt')


def read_bbox(bbox_path):
    data = {}
    for raw in open(bbox_path, encoding='utf-8'):
        line = raw.strip()
        if not line or ' ERROR ' in line:
            continue
        match = re.match(r'file(\d+)\|svg(\d+)\|.*?\|.*?([-+\d.]+) ([-+\d.]+) ([-+\d.]+) ([-+\d.]+)$', line)
        if match:
            values = tuple(float(x) for x in match.groups()[2:6])
            if values[2] >= 0 and values[3] >= 0:
                data[(int(match.group(1)), int(match.group(2)))] = values
    return data


def cropped_viewbox(old, bbox):
    ox, oy, ow, oh = old
    bx, by, bw, bh = bbox
    old_right, old_bottom = ox + ow, oy + oh
    content_right, content_bottom = bx + bw, by + bh

    # 只在原內容已被裁切時向外擴；否則只在舊邊界內消除意外留白。
    nx = math.floor(bx - PAD) if bx < ox else max(ox, math.floor(bx - PAD))
    ny = math.floor(by - PAD) if by < oy else max(oy, math.floor(by - PAD))
    right = math.ceil(content_right + PAD) if content_right > old_right else min(old_right, math.ceil(content_right + PAD))
    bottom = math.ceil(content_bottom + PAD) if content_bottom > old_bottom else min(old_bottom, math.ceil(content_bottom + PAD))
    return nx, ny, max(1, right - nx), max(1, bottom - ny)


def cmd_apply(bbox_path, files):
    data = read_bbox(bbox_path)
    collected = collect(files)
    report = []
    for fi, (path, _) in enumerate(collected):
        src = open(path, encoding='utf-8').read()
        matches = diagram_matches(src)
        out, last, changed = [], 0, 0
        for si, match in enumerate(matches):
            block = match.group(0)
            key = (fi, si)
            if is_preserved(block):
                out.append(src[last:match.end()]); last = match.end()
                report.append((path, si, 'skip: data-viewbox="preserve"'))
                continue
            if key not in data:
                out.append(src[last:match.end()]); last = match.end()
                report.append((path, si, 'skip: no bbox'))
                continue
            vb_match, old = parse_viewbox(block)
            if not old:
                out.append(src[last:match.end()]); last = match.end()
                report.append((path, si, 'skip: invalid viewBox'))
                continue
            new = cropped_viewbox(old, data[key])
            if tuple(new) == tuple(old):
                out.append(src[last:match.end()]); last = match.end()
                continue
            replacement = f'viewBox="{" ".join(fmt(v) for v in new)}"'
            new_block = block[:vb_match.start()] + replacement + block[vb_match.end():]
            changed += 1
            out.append(src[last:match.start()]); out.append(new_block); last = match.end()
        out.append(src[last:])
        open(path, 'w', encoding='utf-8').write(''.join(out))
        report.append((path, changed, f'{len(matches)} 個 diagram SVG；宿主尺寸未改'))
    for item in report:
        print('OK ', *item)
    print('完成。須在實際宿主逐圖複查 stroke、marker、文字及刻意留白。')


def main():
    parser = argparse.ArgumentParser(description='SVG viewBox 整理工具（只改 viewBox）')
    sub = parser.add_subparsers(dest='cmd', required=True)
    gen = sub.add_parser('gen', help='產生瀏覽器量測頁')
    gen.add_argument('files', nargs='+')
    gen.add_argument('-o', '--out', default='/tmp/svg-harness.html')
    apply_cmd = sub.add_parser('apply', help='依 bbox 結果回寫 viewBox')
    apply_cmd.add_argument('bbox')
    apply_cmd.add_argument('files', nargs='+')
    args = parser.parse_args()
    if args.cmd == 'gen':
        cmd_gen(collect(args.files), args.out)
    else:
        cmd_apply(args.bbox, args.files)


if __name__ == '__main__':
    main()
