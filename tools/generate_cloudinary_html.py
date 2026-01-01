#!/usr/bin/env python3
"""
生成使用Cloudinary URL的HTML页面
"""

import json
import sys
from pathlib import Path

def load_cloudinary_urls(bird_name):
    """加载Cloudinary URLs"""
    json_file = Path(f"cloudinary_uploads/{bird_name}_cloudinary_urls.json")
    
    if not json_file.exists():
        print(f"❌ 找不到文件: {json_file}")
        return None
    
    with open(json_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def bird_info_lookup(bird_slug: str, urls_data: dict) -> dict:
    """
    从JSON数据中读取鸟类信息，如果没有则回退为 slug。
    
    Args:
        bird_slug: 鸟类slug (如 'azure_winged_magpie')
        urls_data: JSON数据字典
    
    Returns:
        dict: 包含 'chinese', 'english', 'scientific' 的字典
    """
    # 优先从JSON的bird_info字段读取
    if 'bird_info' in urls_data:
        bird_info = urls_data['bird_info']
        return {
            'chinese': bird_info.get('chinese_name', bird_slug),
            'english': bird_info.get('english_name', bird_slug),
            'scientific': bird_info.get('scientific_name', ''),
        }
    
    # 如果没有bird_info，回退为slug（兼容旧格式）
    return {
        'chinese': bird_slug,
        'english': bird_slug,
        'scientific': '',
    }

def generate_html(bird_name, urls_data):
    """生成HTML页面"""
    
    # 从 JSON 数据中获取鸟类信息
    bird_info = bird_info_lookup(bird_name, urls_data)
    
    # 统计信息（跳过 bird_info 字段）
    total_images = sum(len(images) for key, images in urls_data.items() 
                       if key != 'bird_info' and isinstance(images, list))
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{bird_info['chinese']} - Cloudinary托管版本</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}

        header {{
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}

        h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}

        .subtitle {{
            font-size: 1.2em;
            margin-top: 10px;
        }}

        .info-banner {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }}

        .info-banner strong {{
            font-size: 1.1em;
        }}

        .content {{
            padding: 40px;
        }}

        .advantages {{
            background: #e8f5e9;
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 30px;
            border-left: 4px solid #4caf50;
        }}

        .advantages h3 {{
            color: #2e7d32;
            margin-bottom: 15px;
        }}

        .advantages ul {{
            list-style: none;
            padding: 0;
        }}

        .advantages li {{
            padding: 8px 0;
            padding-left: 25px;
            position: relative;
        }}

        .advantages li::before {{
            content: "✅";
            position: absolute;
            left: 0;
        }}

        .source-section {{
            margin-bottom: 50px;
        }}

        .source-header {{
            display: flex;
            align-items: center;
            padding: 20px;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: 15px;
            margin-bottom: 25px;
        }}

        .source-header h2 {{
            flex: 1;
            color: #2c3e50;
            font-size: 1.8em;
        }}

        .badge {{
            background: #27ae60;
            color: white;
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9em;
        }}

        .image-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 25px;
        }}

        .image-card {{
            background: white;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}

        .image-card:hover {{
            transform: translateY(-10px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.2);
        }}

        .image-card img {{
            width: 100%;
            height: 250px;
            object-fit: cover;
            cursor: pointer;
        }}

        .image-info {{
            padding: 20px;
        }}

        .image-label {{
            background: #3498db;
            color: white;
            padding: 5px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            display: inline-block;
            margin-bottom: 10px;
        }}

        .image-details {{
            font-size: 0.9em;
            color: #666;
            margin-top: 10px;
        }}

        .image-details p {{
            margin: 5px 0;
        }}

        .stats {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
            border-radius: 15px;
            margin-top: 40px;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 25px;
            margin-top: 30px;
        }}

        .stat-card {{
            background: rgba(255,255,255,0.1);
            padding: 25px;
            border-radius: 15px;
            backdrop-filter: blur(10px);
        }}

        .stat-number {{
            font-size: 3em;
            font-weight: bold;
            margin-bottom: 10px;
        }}

        .stat-label {{
            font-size: 1.1em;
            opacity: 0.9;
        }}

        footer {{
            background: #2c3e50;
            color: white;
            text-align: center;
            padding: 30px;
        }}

        footer a {{
            color: #3498db;
            text-decoration: none;
        }}

        footer a:hover {{
            text-decoration: underline;
        }}

        /* 灯箱 */
        .lightbox {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.9);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }}

        .lightbox.active {{
            display: flex;
        }}

        .lightbox img {{
            max-width: 90%;
            max-height: 90%;
            object-fit: contain;
        }}

        .lightbox-close {{
            position: absolute;
            top: 20px;
            right: 40px;
            color: white;
            font-size: 40px;
            cursor: pointer;
            background: rgba(0,0,0,0.5);
            width: 50px;
            height: 50px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        @media (max-width: 768px) {{
            .image-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🐦 {bird_info['chinese']}</h1>
            <div class="subtitle">{bird_info['english']}</div>
            <p style="font-style: italic; opacity: 0.9; margin-top: 10px;">{bird_info['scientific']}</p>
        </header>

        <div class="info-banner">
            <strong>☁️ Cloudinary托管版本</strong> - 所有图片托管在Cloudinary CDN，全球加速访问，无需本地存储
        </div>

        <div class="content">
            <div class="advantages">
                <h3>✨ Cloudinary托管的优势</h3>
                <ul>
                    <li>全球CDN加速，访问速度快</li>
                    <li>自动图片优化和压缩</li>
                    <li>无需本地存储，节省空间</li>
                    <li>支持响应式图片</li>
                    <li>稳定可靠，99.9%可用性</li>
                    <li>免费25GB存储和带宽</li>
                </ul>
            </div>
'''
    
    # 生成各个来源的section
    source_names = {
        'macaulay': 'Macaulay Library（康奈尔鸟类学实验室）',
        'inaturalist': 'iNaturalist（社区科学平台）',
        'birdphotos': 'iNaturalist（替代BirdPhotos）',
        'wikimedia': 'Wikimedia Commons（维基媒体）',
        'avibase': 'Avibase（世界鸟类数据库 - Flickr社区）'
    }
    
    for source, images in urls_data.items():
        # 跳过 bird_info 字段
        if source == 'bird_info' or not isinstance(images, list) or not images:
            continue
        
        source_name = source_names.get(source, source)
        count = len(images)
        
        html += f'''
            <section class="source-section">
                <div class="source-header">
                    <h2>{source_name}</h2>
                    <span class="badge">✓ {count}/{count} 成功</span>
                </div>

                <div class="image-grid">
'''
        
        for idx, img in enumerate(images, 1):
            # Cloudinary URL with transformations
            url = img['url']
            # 添加响应式转换
            url_optimized = url.replace('/upload/', '/upload/c_scale,w_800,q_auto,f_auto/')
            
            html += f'''
                    <div class="image-card">
                        <img src="{url_optimized}" 
                             alt="{bird_info['chinese']} - {source} {idx}"
                             onclick="openLightbox('{url}')"
                             loading="lazy">
                        <div class="image-info">
                            <span class="image-label">图片 {idx}</span>
                            <p><strong>文件:</strong> {img['original_file']}</p>
                            <div class="image-details">
                                <p><strong>尺寸:</strong> {img['width']}x{img['height']}</p>
                                <p><strong>大小:</strong> {img['bytes'] / 1024:.1f}KB</p>
                                <p><strong>格式:</strong> {img['format']}</p>
                            </div>
                        </div>
                    </div>
'''
        
        html += '''
                </div>
            </section>
'''
    
    # 添加统计和footer
    html += f'''
            <section class="stats">
                <h2>📊 统计信息</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-number">{total_images}</div>
                        <div class="stat-label">总图片数</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{len([s for k, s in urls_data.items() if k != 'bird_info' and isinstance(s, list) and s])}</div>
                        <div class="stat-label">数据来源</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">100%</div>
                        <div class="stat-label">CDN托管</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">0KB</div>
                        <div class="stat-label">本地占用</div>
                    </div>
                </div>

                <div style="margin-top: 30px; padding: 20px; background: rgba(255,255,255,0.1); border-radius: 10px;">
                    <p style="font-size: 1.1em;">
                        所有图片托管在 <strong>Cloudinary</strong>，享受全球CDN加速<br>
                        Cloud Name: <code style="background: rgba(0,0,0,0.2); padding: 5px 10px; border-radius: 5px;">dzor6lhz8</code>
                    </p>
                </div>
            </section>
        </div>

        <footer>
            <p><strong>{bird_info['chinese']}</strong> - {bird_info['english']}</p>
            <p style="margin-top: 10px;"><em>{bird_info['scientific']}</em></p>
            <p style="margin-top: 15px; opacity: 0.8;">
                图片托管: <a href="https://cloudinary.com" target="_blank">Cloudinary CDN</a> | 
                生成日期: 2025-10-28
            </p>
        </footer>
    </div>

    <!-- 灯箱 -->
    <div class="lightbox" id="lightbox" onclick="closeLightbox()">
        <span class="lightbox-close">&times;</span>
        <img id="lightbox-img" src="" alt="">
    </div>

    <script>
        function openLightbox(src) {{
            document.getElementById('lightbox').classList.add('active');
            document.getElementById('lightbox-img').src = src;
            event.stopPropagation();
        }}

        function closeLightbox() {{
            document.getElementById('lightbox').classList.remove('active');
        }}

        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                closeLightbox();
            }}
        }});

        // 图片加载统计
        window.addEventListener('load', function() {{
            const images = document.querySelectorAll('.image-card img');
            let loaded = 0;
            let failed = 0;

            images.forEach(img => {{
                if (img.complete) {{
                    loaded++;
                }} else {{
                    img.addEventListener('load', () => loaded++);
                    img.addEventListener('error', () => failed++);
                }}
            }});

            setTimeout(() => {{
                console.log(`图片加载统计: 成功 ${{loaded}}, 失败 ${{failed}}, 总计 ${{images.length}}`);
            }}, 3000);
        }});
    </script>
</body>
</html>
'''
    
    return html

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python3 generate_cloudinary_html.py <bird_name>")
        print("示例: python3 generate_cloudinary_html.py marsh_tit")
        print("     python3 generate_cloudinary_html.py bluetail")
        sys.exit(1)
    
    bird_name = sys.argv[1]
    
    print(f"\n🔨 生成 {bird_name} 的Cloudinary HTML页面...")
    
    # 加载URL数据
    urls_data = load_cloudinary_urls(bird_name)
    if not urls_data:
        sys.exit(1)
    
    # 生成HTML
    html_content = generate_html(bird_name, urls_data)
    
    # 保存文件
    output_dir = Path(f"examples/{bird_name}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "gallery_cloudinary.html"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ HTML页面已生成: {output_file}")
    print(f"\n打开查看:")
    print(f"  open {output_file}")
    
    return output_file

if __name__ == "__main__":
    main()
