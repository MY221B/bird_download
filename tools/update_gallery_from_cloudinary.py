#!/usr/bin/env python3
"""
从 cloudinary_uploads/*_cloudinary_urls.json 生成/更新 examples/gallery_all_cloudinary.html：
- 补齐缺失的鸟种；
- 缺失的鸟种排在现有列表前面；
- 保留并注入“多选与删除清单（仅记录）”前端功能。
"""

from pathlib import Path
import re
import json


UPLOAD_DIR = Path('cloudinary_uploads')
OUT_FILE = Path('examples/gallery_all_cloudinary.html')


def load_all_birds(upload_dir: Path) -> dict:
    data = {}
    for jf in sorted(upload_dir.glob('*_cloudinary_urls.json')):
        slug = jf.stem.replace('_cloudinary_urls', '')
        try:
            data[slug] = json.loads(jf.read_text(encoding='utf-8'))
        except Exception:
            continue
    return data


def parse_existing_order(html_text: str) -> list:
    # 从 nav-item data-target 提取现有顺序
    return re.findall(r'data-target="([^"]+)"', html_text)


def bird_info_lookup(slug: str, data: dict) -> dict:
    """从多个来源获取鸟类信息，优先使用JSON中的bird_info"""
    info = data.get('bird_info') or {}
    
    chinese = info.get('chinese_name', '')
    english = info.get('english_name', '')
    scientific = info.get('scientific_name', '')
    
    # 如果缺少英文名或学名，尝试从其他来源获取
    if not english or not scientific:
        # 尝试从all_birds.csv读取
        csv_file = Path('all_birds.csv')
        if csv_file.exists():
            try:
                import csv
                with open(csv_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
                    if data_lines:
                        reader = csv.DictReader(data_lines)
                        for row in reader:
                            if row.get('slug') == slug:
                                if not english:
                                    english = row.get('english_name', '').strip('"')
                                if not scientific:
                                    scientific = row.get('scientific_name', '').strip('"')
                                if not chinese:
                                    chinese = row.get('chinese_name', '').strip('"')
                                break
            except Exception:
                pass
        
        # 尝试从location_birds JSON文件读取
        if not english or not scientific:
            location_birds_dir = Path('feather-flash-quiz/location_birds')
            if location_birds_dir.exists():
                for json_file in location_birds_dir.rglob(f'{slug}_cloudinary_urls.json'):
                    try:
                        loc_data = json.loads(json_file.read_text(encoding='utf-8'))
                        loc_info = loc_data.get('bird_info') or {}
                        if not chinese:
                            chinese = loc_info.get('chinese_name', '')
                        if not english:
                            english = loc_info.get('english_name', '')
                        if not scientific:
                            scientific = loc_info.get('scientific_name', '')
                        if chinese and english:
                            break
                    except Exception:
                        continue
    
    # 如果还是没有，使用slug作为默认值
    return {
        'chinese': chinese or slug,
        'english': english or slug,
        'scientific': scientific or '',
    }


def build_html(all_data: dict, ordered_slugs: list, highlight_slugs: list = None) -> str:
    def total_images(d: dict) -> int:
        return sum(len(v or []) for k, v in d.items() if k != 'bird_info')

    # 只标红传入的 highlight_slugs，清除所有旧的标红
    highlight_set = set(highlight_slugs or [])
    
    # 侧边栏
    nav_items = []
    sections = []
    for idx, slug in enumerate(ordered_slugs, start=1):
        urls = all_data[slug]
        info = bird_info_lookup(slug, urls)
        # 左侧列表：中文名在上，英文名在下
        chinese_name = info["chinese"] if info["chinese"] != slug else slug
        english_name = info["english"] if info["english"] != slug else ""
        
        # 只对在 highlight_set 中的鸟类添加 highlight 类，其他都不添加（清除旧的标红）
        highlight_class = " highlight" if slug in highlight_set else ""
        
        if english_name:
            nav_items.append(f'<div class="nav-item{highlight_class}" data-target="{slug}">{chinese_name}<br><span class="nav-sub">{english_name}</span></div>')
        else:
            nav_items.append(f'<div class="nav-item{highlight_class}" data-target="{slug}">{chinese_name}</div>')

        parts = []
        parts.append(f'''
            <div class="bird-header">
                <h1>🐦 {info['chinese']}</h1>
                <div class="subtitle">{info['english']}</div>
                <p class="sci"><em>{info['scientific']}</em></p>
            </div>
        ''')

        source_names = {
            'macaulay': 'Macaulay Library（康奈尔鸟类学实验室）',
            'inaturalist': 'iNaturalist（社区科学平台）',
            'birdphotos': 'iNaturalist（替代BirdPhotos）',
            'wikimedia': 'Wikimedia Commons（维基媒体）',
            'avibase': 'Avibase（世界鸟类数据库 - Flickr社区）',
        }

        for source, images in urls.items():
            if source == 'bird_info' or not images:
                continue
            parts.append(f'''
                <section class="source-section">
                    <div class="source-header">
                        <h2>{source_names.get(source, source)}</h2>
                        <span class="badge">✓ {len(images)}/{len(images)} 成功</span>
                    </div>
                    <div class="image-grid">
            ''')

            for i, img in enumerate(images, 1):
                url = img['url']
                url_opt = url.replace('/upload/', '/upload/c_scale,w_800,q_auto,f_auto/')
                parts.append(f'''
                        <div class="image-card">
                            <img src="{url_opt}" alt="{info['chinese']} - {source} {i}" onclick="openLightbox('{url}')" loading="lazy">
                            <div class="image-info">
                                <span class="image-label">图片 {i}</span>
                                <p><strong>文件:</strong> {img.get('original_file','')}</p>
                                <div class="image-details">
                                    <p><strong>尺寸:</strong> {img.get('width','?')}x{img.get('height','?')}</p>
                                    <p><strong>大小:</strong> {round((img.get('bytes') or 0)/1024,1)}KB</p>
                                    <p><strong>格式:</strong> {img.get('format','')}</p>
                                </div>
                            </div>
                        </div>
                ''')
            parts.append('''
                    </div>
                </section>
            ''')

        total = total_images(urls)
        parts.append(f'''
            <section class="stats">
                <h2>📊 统计信息</h2>
                <div class="stats-grid">
                    <div class="stat-card"><div class="stat-number">{total}</div><div class="stat-label">总图片数</div></div>
                    <div class="stat-card"><div class="stat-number">{len([s for s in urls.values() if isinstance(s, list) and s])}</div><div class="stat-label">数据来源</div></div>
                    <div class="stat-card"><div class="stat-number">100%</div><div class="stat-label">CDN托管</div></div>
                </div>
            </section>
        ''')

        sections.append(f'<section id="{slug}" class="bird-section {"active" if idx==1 else ""}">\n' + "\n".join(parts) + '\n</section>')

    # 页面骨架 + 选择UI（与现有页面一致）
    html_tpl = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>小鸟记忆卡 - Cloudinary 总览</title>
  <style>
    :root {{ --sidebar-w: 300px; }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background: #f6f7fb; color: #2c3e50; }}
    .layout {{ display: flex; min-height: 100vh; }}
    .sidebar {{ width: var(--sidebar-w); background: #1e293b; color: #fff; padding: 20px; position: sticky; top: 0; height: 100vh; overflow-y: auto; }}
    .brand {{ font-size: 20px; font-weight: 700; margin-bottom: 16px; }}
    .nav-item {{ padding: 12px 10px; border-radius: 8px; cursor: pointer; margin: 6px 0; background: #0f172a; }}
    .nav-item:hover {{ background: #111827; }}
    .nav-item.active {{ background: #2563eb; }}
    .nav-item.highlight {{ background: #7f1d1d; color: #fecaca; font-weight: 600; }}
    .nav-item.highlight:hover {{ background: #991b1b; }}
    .nav-item.highlight.active {{ background: #dc2626; color: #fff; }}
    .nav-sub {{ font-size: 12px; opacity: .8; }}
    .content {{ flex: 1; padding: 24px; }}
    .bird-section {{ display: none; }}
    .bird-section.active {{ display: block; }}
    .bird-header {{ background: linear-gradient(135deg,#1e3c72 0%,#2a5298 100%); color:#fff; padding:24px; border-radius: 12px; margin-bottom: 18px; }}
    .bird-header h1 {{ font-size: 28px; margin-bottom: 4px; }}
    .bird-header .subtitle {{ opacity:.95 }}
    .bird-header .sci {{ opacity:.9; margin-top: 6px; }}
    .source-section {{ margin: 18px 0 28px; }}
    .source-header {{ display:flex; align-items:center; padding:14px; background:#eef2ff; border-radius:10px; margin-bottom: 14px; }}
    .source-header h2 {{ flex:1; font-size:18px; color:#1f2a44; }}
    .badge {{ background:#22c55e; color:#fff; padding:6px 12px; border-radius: 999px; font-weight:700; font-size:12px; }}
    .image-grid {{ display:grid; grid-template-columns: repeat(auto-fit,minmax(260px,1fr)); gap:16px; }}
    .image-card {{ background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 4px 16px rgba(0,0,0,.06); position: relative; }}
    .image-card img {{ width:100%; height:200px; object-fit:cover; cursor:pointer; }}
    .image-info {{ padding:12px; }}
    .image-label {{ background:#3b82f6; color:#fff; padding:2px 8px; border-radius:12px; font-size:12px; display:inline-block; margin-bottom:6px; }}
    .image-details p {{ font-size:12px; color:#64748b; margin:3px 0; }}
    .stats {{ background: linear-gradient(135deg,#667eea 0%,#764ba2 100%); color:#fff; padding:20px; border-radius: 12px; }}
    .lightbox {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.9); z-index:1000; justify-content:center; align-items:center; }}
    .lightbox.active {{ display:flex; }}
    .lightbox img {{ max-width:90%; max-height:90%; object-fit:contain; }}
    .lightbox-close {{ position:absolute; top:20px; right:30px; color:#fff; font-size:32px; cursor:pointer; }}
    @media (max-width: 900px) {{ :root {{ --sidebar-w: 220px; }} .image-card img {{ height: 180px; }} }}
    /* selection UI */
    .select-overlay {{ position:absolute; top:8px; left:8px; display:flex; align-items:center; gap:6px; z-index:5; }}
    .select-overlay input[type="checkbox"] {{ width:20px; height:20px; accent-color:#ef4444; cursor:pointer; }}
    .image-card.selected {{ outline:3px solid #ef4444; outline-offset:-3px; }}
    .img-toolbar {{ position: fixed; top:14px; right:16px; z-index:1100; display:flex; gap:8px; align-items:center; background:rgba(30,41,59,.9); color:#fff; padding:10px 12px; border-radius:12px; box-shadow:0 6px 24px rgba(0,0,0,.2); }}
    .img-toolbar button {{ background:#ef4444; border:none; color:#fff; padding:8px 12px; border-radius:999px; cursor:pointer; font-weight:700; }}
    .img-toolbar .secondary {{ background:#334155; }}
    .img-toolbar .counter {{ font-size:12px; opacity:.9; padding:0 6px; }}
    .delete-list-panel {{ position:fixed; top:64px; right:16px; width:min(520px, calc(100vw - 40px)); max-height:50vh; z-index:1100; display:none; }}
    .delete-list-panel.active {{ display:block; }}
    .delete-list-panel textarea {{ width:100%; height:220px; padding:10px; border-radius:12px; border:1px solid #cbd5e1; background:#0b1220; color:#e2e8f0; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size:12px; }}
  </style>
</head>
<body>
  <div class="img-toolbar" id="img-toolbar" style="display:none">
    <span class="counter" id="sel-counter">已选 0 张</span>
    <button class="secondary" id="btn-clear">清空选择</button>
    <button class="secondary" id="btn-select-visible">全选当前分组</button>
    <button id="btn-copy">复制删除清单</button>
  </div>
  <div class="delete-list-panel" id="delete-list-panel">
    <textarea id="delete-json" readonly></textarea>
  </div>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">小鸟记忆卡 · Cloudinary</div>
      %%NAV%%
    </aside>
    <main class="content">
      %%SECTIONS%%
    </main>
  </div>
  <div class="lightbox" id="lightbox" onclick="closeLightbox()">
    <span class="lightbox-close">&times;</span>
    <img id="lightbox-img" src="" alt="">
  </div>
  <script>
  function activateBird(slug) {
    document.querySelectorAll('.bird-section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const sec = document.getElementById(slug); if (sec) sec.classList.add('active');
    const nav = Array.from(document.querySelectorAll('.nav-item')).find(n => n.dataset.target===slug); if (nav) nav.classList.add('active');
  }
  document.querySelectorAll('.nav-item').forEach(n => n.addEventListener('click', () => activateBird(n.dataset.target)));
  const firstNav = document.querySelector('.nav-item'); if (firstNav) activateBird(firstNav.dataset.target);
  function openLightbox(src) {
    document.getElementById('lightbox').classList.add('active');
    document.getElementById('lightbox-img').src = src;
    event.stopPropagation();
  }
  function closeLightbox() {
    document.getElementById('lightbox').classList.remove('active');
  }
  window.openLightbox = openLightbox; window.closeLightbox = closeLightbox;
  (function(){
    const toolbar = document.getElementById('img-toolbar');
    const counter = document.getElementById('sel-counter');
    const btnClear = document.getElementById('btn-clear');
    const btnCopy = document.getElementById('btn-copy');
    const btnSelectVisible = document.getElementById('btn-select-visible');
    const panel = document.getElementById('delete-list-panel');
    const txt = document.getElementById('delete-json');
    const selected = new Set();
    function ensureToolbarVisibility() { toolbar.style.display = 'flex'; counter.textContent = `已选 ${selected.size} 张`; }
    function getPublicIdFromUrl(url) {
      try { const u = new URL(url); const parts = u.pathname.split('/'); const uploadIdx = parts.indexOf('upload'); let i = uploadIdx + 1; while (i < parts.length && !/^v\d+/.test(parts[i])) i++; if (i >= parts.length) return null; const afterVersion = parts.slice(i + 1).join('/'); if (!afterVersion) return null; const lastDot = afterVersion.lastIndexOf('.'); const withoutExt = lastDot > 0 ? afterVersion.slice(0, lastDot) : afterVersion; return withoutExt; } catch(_) { return null; }
    }
    function attachCheckbox(card) {
      if (card.querySelector('.select-overlay')) return; const img = card.querySelector('img'); if (!img) return; const publicId = getPublicIdFromUrl(img.src); if (!publicId) return; card.dataset.publicId = publicId; const overlay = document.createElement('div'); overlay.className = 'select-overlay'; const cb = document.createElement('input'); cb.type = 'checkbox'; overlay.appendChild(cb); card.appendChild(overlay);
      function toggleSelected(force) { const willSelect = force !== undefined ? force : !cb.checked; cb.checked = willSelect; if (willSelect) { card.classList.add('selected'); selected.add(publicId);} else { card.classList.remove('selected'); selected.delete(publicId);} ensureToolbarVisibility(); }
      cb.addEventListener('click', (e) => { e.stopPropagation(); toggleSelected(cb.checked); });
      img.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); toggleSelected(); });
    }
    document.querySelectorAll('.image-card').forEach(attachCheckbox);
    btnSelectVisible.addEventListener('click', () => { const active = document.querySelector('.bird-section.active'); if (!active) return; active.querySelectorAll('.image-card').forEach(card => { attachCheckbox(card); const cb = card.querySelector('.select-overlay input[type="checkbox"]'); if (cb && !cb.checked) cb.click(); }); });
    btnClear.addEventListener('click', () => { document.querySelectorAll('.image-card.selected').forEach(card => { const cb = card.querySelector('.select-overlay input[type="checkbox"]'); if (cb) { cb.checked = false; } card.classList.remove('selected'); }); selected.clear(); ensureToolbarVisibility(); panel.classList.remove('active'); });
    btnCopy.addEventListener('click', async () => { const list = Array.from(selected).map(pid => ({ public_id: pid })); const json = JSON.stringify({ count: list.length, items: list }, null, 2); txt.value = json; panel.classList.add('active'); try { await navigator.clipboard.writeText(json); } catch(_) {} });
    ensureToolbarVisibility();
  })();
  </script>
</body>
</html>
'''
    html = html_tpl.replace('%%NAV%%', ''.join(nav_items)).replace('%%SECTIONS%%', ''.join(sections))
    # 将为了避免字符串格式化冲突而写的成对花括号还原为单花括号
    html = html.replace('{{', '{').replace('}}', '}')
    return html


def main(highlight_slugs=None, priority_slugs=None):
    all_data = load_all_birds(UPLOAD_DIR)
    if not all_data:
        raise SystemExit('未找到任何 *_cloudinary_urls.json')

    existing_order = []
    if OUT_FILE.exists():
        existing_order = parse_existing_order(OUT_FILE.read_text(encoding='utf-8'))

    all_slugs = list(all_data.keys())
    priority_set = set(priority_slugs or [])
    highlight_set = set(highlight_slugs or [])
    
    # 排序逻辑：
    # 1. 首先排 priority_slugs（需要下载/检查的鸟类）
    # 2. 然后排 missing（新鸟种，但不在 priority_slugs 中）
    # 3. 最后排 existing_order 中的其他鸟类
    priority_list = [s for s in (priority_slugs or []) if s in all_slugs]
    missing = [s for s in all_slugs if s not in existing_order and s not in priority_set]
    existing_list = [s for s in existing_order if s in all_slugs and s not in priority_set]
    final_order = priority_list + missing + existing_list

    html = build_html(all_data, final_order, highlight_slugs or [])
    OUT_FILE.write_text(html, encoding='utf-8')
    
    if highlight_slugs:
        priority_info = f"，其中 {len(priority_list)} 个需要下载/检查的鸟类排在最前面" if priority_list else ""
        print(f'✅ 已更新 {OUT_FILE}，新增 {len(missing)} 个鸟种，全部排在列表顶部（{len(highlight_slugs)} 个鸟种已标红{priority_info}）')
    else:
        priority_info = f"，其中 {len(priority_list)} 个需要下载/检查的鸟类排在最前面" if priority_list else ""
        print(f'✅ 已更新 {OUT_FILE}，新增 {len(missing)} 个鸟种，全部排在列表顶部{priority_info}')


if __name__ == '__main__':
    main()


