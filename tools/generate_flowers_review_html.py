#!/usr/bin/env python3
"""从 springFlowers.ts + public/flowers 扫描结果生成 public/flowers-review.html。"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TS_PATH = REPO_ROOT / "feather-flash-quiz/src/data/springFlowers.ts"
FLOWERS_DIR = REPO_ROOT / "feather-flash-quiz/public/flowers"
OUT_PATH = REPO_ROOT / "feather-flash-quiz/public/flowers-review.html"
REPO_PREFIX = "feather-flash-quiz/public"

IMG_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def parse_flower_order_and_names(ts_text: str) -> list[tuple[str, str]]:
    """按 FLOWERS 对象在文件中的出现顺序解析 id 与中文名。"""
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"^\s{2}([a-z_][a-z0-9_]*):\s*\{", ts_text, re.MULTILINE):
        key = m.group(1)
        chunk = ts_text[m.end() : m.end() + 500]
        nm = re.search(
            r"^\s+id:\s*'[^']+',\s*\n\s+name:\s*'((?:[^'\\]|\\.)*)'",
            chunk,
            re.MULTILINE,
        )
        if nm:
            name = nm.group(1).replace("\\'", "'")
            out.append((key, name))
    return out


def natural_sort_key(path: Path):
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", path.name)
    ]


def list_flower_images(flower_id: str) -> list[str]:
    d = FLOWERS_DIR / flower_id
    if not d.is_dir():
        return []
    files: list[Path] = []
    for p in d.iterdir():
        if p.is_file() and p.suffix.lower() in IMG_SUFFIXES:
            files.append(p)
    files.sort(key=natural_sort_key)
    return [p.name for p in files]


def main() -> None:
    ts_text = TS_PATH.read_text(encoding="utf-8")
    ordered = parse_flower_order_and_names(ts_text)
    if not ordered:
        raise SystemExit(f"未从 {TS_PATH} 解析到花卉条目")

    seen_dirs = {fid for fid, _ in ordered}
    extra_dirs = sorted(
        p.name
        for p in FLOWERS_DIR.iterdir()
        if p.is_dir() and p.name not in seen_dirs
    )

    flowers_payload: list[dict] = []
    for fid, zh in ordered:
        images = list_flower_images(fid)
        flowers_payload.append({"id": fid, "name": zh, "images": images})

    for fid in extra_dirs:
        images = list_flower_images(fid)
        flowers_payload.append(
            {
                "id": fid,
                "name": f"（未在 springFlowers.ts 注册：{fid}）",
                "images": images,
            }
        )

    now = time.time()
    cache_bust = str(int(now))
    ts_ms = int(now * 1000)
    flowers_json = json.dumps(flowers_payload, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>春季花卉图片检阅</title>
  <style>
    :root {{
      --bg: #f4f2ee;
      --card: #fff;
      --text: #1a1a1a;
      --muted: #5c5c5c;
      --accent: #2d6a4f;
      --warn: #c1121f;
      --border: #ddd8d0;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 1.25rem 1.25rem 6rem;
    }}
    h1 {{
      font-size: 1.35rem;
      font-weight: 650;
      margin: 0 0 0.35rem;
    }}
    .hint {{
      color: var(--muted);
      font-size: 0.875rem;
      max-width: 52rem;
      margin-bottom: 1.25rem;
    }}
    .meta-gen {{
      font-size: 0.75rem;
      color: var(--muted);
      margin-bottom: 1rem;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 0.75rem;
      align-items: center;
      margin-bottom: 1rem;
    }}
    .toolbar button, .toolbar label {{
      font: inherit;
      cursor: pointer;
    }}
    .toolbar button {{
      border: 1px solid var(--border);
      background: var(--card);
      padding: 0.45rem 0.85rem;
      border-radius: 8px;
    }}
    .toolbar button.primary {{
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }}
    .toolbar button:disabled {{
      opacity: 0.45;
      cursor: not-allowed;
    }}
    #search {{
      flex: 1;
      min-width: 12rem;
      padding: 0.45rem 0.65rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      font: inherit;
    }}
    .section-title {{
      font-size: 0.95rem;
      font-weight: 600;
      margin: 1.5rem 0 0.65rem;
      padding-bottom: 0.35rem;
      border-bottom: 2px solid var(--accent);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 0.85rem;
    }}
    .card {{
      background: var(--card);
      border: 2px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      transition: border-color 0.15s, box-shadow 0.15s;
    }}
    .card.flagged {{
      border-color: var(--warn);
      box-shadow: 0 0 0 1px rgba(193, 18, 31, 0.15);
    }}
    .card.missing {{
      border-style: dashed;
      opacity: 0.85;
    }}
    .card-head {{
      display: flex;
      align-items: flex-start;
      gap: 0.5rem;
      padding: 0.5rem 0.6rem 0;
    }}
    .card-head input {{
      width: 1.1rem;
      height: 1.1rem;
      margin-top: 0.15rem;
      flex-shrink: 0;
    }}
    .meta {{
      flex: 1;
      min-width: 0;
    }}
    .meta .id {{
      font-size: 0.72rem;
      font-family: ui-monospace, monospace;
      color: var(--muted);
      word-break: break-all;
    }}
    .meta .cn {{
      font-weight: 600;
      font-size: 0.9rem;
    }}
    .meta .path {{
      font-size: 0.68rem;
      color: var(--muted);
      word-break: break-all;
    }}
    .thumb-wrap {{
      aspect-ratio: 4/3;
      background: #e8e6e1;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .thumb-wrap img {{
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      display: block;
    }}
    .placeholder {{
      color: var(--muted);
      font-size: 0.8rem;
      padding: 1rem;
      text-align: center;
    }}
    .sticky {{
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      padding: 0.65rem 1rem;
      background: rgba(255, 255, 255, 0.92);
      border-top: 1px solid var(--border);
      backdrop-filter: blur(8px);
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
      justify-content: space-between;
      z-index: 20;
    }}
    .sticky .count {{
      font-size: 0.9rem;
      color: var(--muted);
    }}
    .sticky .count strong {{ color: var(--warn); }}
    textarea#preview {{
      display: none;
    }}
    .toast {{
      position: fixed;
      bottom: 4.5rem;
      left: 50%;
      transform: translateX(-50%) translateY(120%);
      background: #1a1a1a;
      color: #fff;
      padding: 0.5rem 1rem;
      border-radius: 8px;
      font-size: 0.875rem;
      opacity: 0;
      transition: transform 0.25s, opacity 0.25s;
      z-index: 30;
      pointer-events: none;
    }}
    .toast.show {{
      transform: translateX(-50%) translateY(0);
      opacity: 1;
    }}
  </style>
</head>
<body>
  <h1>春季花卉图片检阅</h1>
  <p class="hint">
    用浏览器直接打开本文件即可预览（需与 <code>flowers</code> 文件夹在同一目录）。勾选认为不合适或需替换的图片，点击下方按钮复制文本，粘贴给助手即可批量删除或替换。
    更新图片后可运行 <code>python3 tools/generate_flowers_review_html.py</code> 重新生成本页。
  </p>
  <p class="meta-gen" id="gen-line"></p>

  <div class="toolbar">
    <input type="search" id="search" placeholder="按中文名或 id 筛选…" autocomplete="off" />
    <button type="button" id="btn-clear-checks">清除全部勾选</button>
    <button type="button" id="btn-copy" class="primary" disabled>复制已勾选信息</button>
  </div>

  <div id="sections"></div>

  <textarea id="preview" readonly aria-hidden="true"></textarea>

  <div class="sticky">
    <span class="count">已勾选 <strong id="count-num">0</strong> 张</span>
    <button type="button" id="btn-copy-2" class="primary" disabled>复制已勾选信息</button>
  </div>

  <div id="toast" class="toast" role="status">已复制到剪贴板</div>

  <script>
    const FLOWERS = {flowers_json};
    const CACHE_BUST = {json.dumps(cache_bust)};
    const REPO_PREFIX = {json.dumps(REPO_PREFIX)};
    const GENERATED_AT = new Date({ts_ms});

    function buildItems() {{
      const items = [];
      for (const f of FLOWERS) {{
        if (f.images.length === 0) {{
          items.push({{
            key: `${{f.id}}__missing`,
            flowerId: f.id,
            name: f.name,
            fileName: '(无图片文件)',
            imgSrc: '',
            repoPath: `${{REPO_PREFIX}}/flowers/${{f.id}}/`,
            missing: true,
          }});
          continue;
        }}
        for (const fileName of f.images) {{
          const relPublic = `flowers/${{f.id}}/${{fileName}}`;
          items.push({{
            key: `${{f.id}}__${{fileName}}`,
            flowerId: f.id,
            name: f.name,
            fileName,
            imgSrc: `./${{relPublic}}?v=${{CACHE_BUST}}`,
            repoPath: `${{REPO_PREFIX}}/${{relPublic}}`,
            missing: false,
          }});
        }}
      }}
      return items;
    }}

    const allItems = buildItems();
    const sectionsEl = document.getElementById('sections');
    const searchEl = document.getElementById('search');
    const countNum = document.getElementById('count-num');
    const btnCopy = document.getElementById('btn-copy');
    const btnCopy2 = document.getElementById('btn-copy-2');
    const btnClear = document.getElementById('btn-clear-checks');
    const preview = document.getElementById('preview');
    const toast = document.getElementById('toast');
    const genLine = document.getElementById('gen-line');

    genLine.textContent =
      '生成时间：' +
      GENERATED_AT.toLocaleString('zh-CN') +
      ' · 共 ' +
      allItems.filter((i) => !i.missing).length +
      ' 张图（含缓存参数 v=' +
      CACHE_BUST +
      '）';

    const checkState = new Map();

    function render() {{
      const q = (searchEl.value || '').trim().toLowerCase();
      sectionsEl.innerHTML = '';

      for (const f of FLOWERS) {{
        const flowerItems = allItems.filter((i) => i.flowerId === f.id);
        const visible = flowerItems.filter((i) => {{
          if (!q) return true;
          return (
            f.id.toLowerCase().includes(q) ||
            f.name.toLowerCase().includes(q) ||
            f.name.includes(searchEl.value.trim())
          );
        }});
        if (visible.length === 0) continue;

        const h2 = document.createElement('h2');
        h2.className = 'section-title';
        h2.textContent = `${{f.name}}（${{f.id}}）`;
        sectionsEl.appendChild(h2);

        const grid = document.createElement('div');
        grid.className = 'grid';

        for (const item of visible) {{
          const card = document.createElement('article');
          card.className = 'card' + (item.missing ? ' missing' : '');
          card.dataset.key = item.key;

          const checked = checkState.get(item.key) === true;
          if (checked) card.classList.add('flagged');

          const safeLabel = item.missing
            ? '无图片'
            : item.fileName;
          card.innerHTML = `
            <div class="card-head">
              <input type="checkbox" ${{checked ? 'checked' : ''}} aria-label="标记为需处理：${{item.name}} ${{safeLabel}}" />
              <div class="meta">
                <div class="cn">${{item.name}} · ${{safeLabel}}</div>
                <div class="id">${{item.flowerId}}</div>
                <div class="path">${{item.repoPath}}</div>
              </div>
            </div>
            <div class="thumb-wrap">
              ${{item.missing
                ? '<span class="placeholder">该目录下未找到图片文件</span>'
                : `<img src="${{item.imgSrc}}" alt="${{item.name}} ${{item.fileName}}" loading="lazy" />`}}
            </div>
          `;

          const cb = card.querySelector('input[type="checkbox"]');
          cb.addEventListener('change', () => {{
            checkState.set(item.key, cb.checked);
            card.classList.toggle('flagged', cb.checked);
            updateCount();
          }});

          grid.appendChild(card);
        }}
        sectionsEl.appendChild(grid);
      }}
    }}

    function selectedItems() {{
      return allItems.filter((i) => checkState.get(i.key) === true);
    }}

    function buildCopyText() {{
      const lines = [
        '以下春季花卉图片需删除或替换（由 flowers-review.html 勾选生成）：',
        '',
        'flower_id\\tfile_name\\trepo_path\\tname_zh',
      ];
      for (const i of selectedItems()) {{
        lines.push(
          `${{i.flowerId}}\\t${{i.fileName}}\\t${{i.repoPath}}\\t${{i.name}}`
        );
      }}
      lines.push('');
      lines.push('说明：file_name 为 public/flowers/<flower_id>/ 下的文件名；无文件时 repo_path 可能仅为目录。');
      return lines.join('\\n');
    }}

    function updateCount() {{
      const n = selectedItems().length;
      countNum.textContent = String(n);
      btnCopy.disabled = n === 0;
      btnCopy2.disabled = n === 0;
    }}

    function showToast() {{
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 2000);
    }}

    async function copySelected() {{
      const text = buildCopyText();
      preview.value = text;
      try {{
        await navigator.clipboard.writeText(text);
        showToast();
      }} catch {{
        preview.style.display = 'block';
        preview.style.width = '100%';
        preview.style.minHeight = '8rem';
        preview.select();
        document.execCommand('copy');
        preview.style.display = 'none';
        showToast();
      }}
    }}

    searchEl.addEventListener('input', () => render());
    btnClear.addEventListener('click', () => {{
      checkState.clear();
      render();
      updateCount();
    }});
    btnCopy.addEventListener('click', copySelected);
    btnCopy2.addEventListener('click', copySelected);

    render();
    updateCount();
  </script>
</body>
</html>
"""

    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(flowers_payload)} 个花卉条目)")


if __name__ == "__main__":
    main()
