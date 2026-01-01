#!/usr/bin/env python3
"""
上传鸟类图片到Cloudinary
"""

import os
import sys
import re
import json
import cloudinary
import cloudinary.uploader
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # 如果未安装 requests，Macaulay 署名获取功能将不可用

# Cloudinary配置
CLOUD_NAME = "dzor6lhz8"
API_KEY = "972579995456539"
API_SECRET = "pKXHi4_VR4fasuJ0AanitLGWfCM"

# 配置Cloudinary
cloudinary.config(
    cloud_name=CLOUD_NAME,
    api_key=API_KEY,
    api_secret=API_SECRET,
    secure=True
)

def upload_bird_images(bird_name, base_path, bird_info=None):
    """
    上传指定鸟类的所有图片
    
    Args:
        bird_name: 鸟类名称（如 'marsh_tit', 'bluetail'）
        base_path: 图片基础路径
        bird_info: 鸟类信息字典 {'chinese_name': ..., 'english_name': ..., 'scientific_name': ...}
    
    Returns:
        dict: 包含所有上传后的URL信息（包含署名元数据和鸟类信息）
    """
    results = {
        'macaulay': [],
        'inaturalist': [],
        'birdphotos': [],
        'wikimedia': [],
        'avibase': []
    }
    
    # 添加鸟类信息到结果中（如果提供）
    if bird_info:
        results['bird_info'] = {
            'slug': bird_name,
            'chinese_name': bird_info.get('chinese_name', ''),
            'english_name': bird_info.get('english_name', ''),
            'scientific_name': bird_info.get('scientific_name', '')
        }
    
    bird_path = Path(base_path) / bird_name
    
    if not bird_path.exists():
        print(f"❌ 路径不存在: {bird_path}")
        return results
    
    # 读取下载时保存的元数据
    download_metadata = {}
    metadata_file = bird_path / "download_metadata.json"
    if metadata_file.exists():
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                download_metadata = json.load(f)
            print(f"📄 找到下载元数据文件")
        except Exception as e:
            print(f"⚠️  读取元数据失败: {e}")
            download_metadata = {}
    
    print(f"\n{'='*60}")
    print(f"开始上传: {bird_name}")
    print(f"Cloudinary: cloud_name={CLOUD_NAME}")
    print(f"本地目录: {bird_path}")
    print(f"{'='*60}\n")
    
    # 遍历各个来源
    for source in ['macaulay', 'inaturalist', 'birdphotos', 'wikimedia', 'avibase']:
        source_path = bird_path / source
        
        if not source_path.exists():
            print(f"⏭️  跳过不存在的目录: {source}")
            continue
        
        print(f"\n📁 处理来源: {source}")
        print("-" * 60)
        
        # 获取所有图片文件
        image_files = list(source_path.glob("*.jpg")) + list(source_path.glob("*.jpeg")) + list(source_path.glob("*.png"))
        print(f"  待上传文件数: {len(image_files)}")
        
        if not image_files:
            print(f"  ⚠️  没有找到图片文件")
            continue
        
        uploaded_count = 0
        for img_file in sorted(image_files):
            try:
                # 构建Cloudinary路径
                folder = f"bird-gallery/{bird_name}/{source}"
                public_id = img_file.stem  # 不含扩展名的文件名
                
                print(f"\n  📤 上传: {img_file.name}")
                print(f"     目标: {folder}/{public_id}")
                
                # 上传到Cloudinary
                result = cloudinary.uploader.upload(
                    str(img_file),
                    folder=folder,
                    public_id=public_id,
                    overwrite=True,
                    resource_type="image",
                    # 自动优化
                    quality="auto",
                    fetch_format="auto"
                )
                
                # 保存结果
                image_info = {
                    'original_file': img_file.name,
                    'url': result['secure_url'],
                    'public_id': result['public_id'],
                    'width': result['width'],
                    'height': result['height'],
                    'format': result['format'],
                    'bytes': result['bytes']
                }
                
                # 合并下载时的元数据
                attribution = find_attribution_for_file(
                    img_file.name, source, download_metadata
                )
                image_info['attribution'] = attribution
                
                results[source].append(image_info)
                
                size_kb = result['bytes'] / 1024
                print(f"     ✅ 成功!")
                print(f"     URL: {result['secure_url']}")
                print(f"     尺寸: {result['width']}x{result['height']}")
                print(f"     大小: {size_kb:.1f}KB")
                uploaded_count += 1
                
            except Exception as e:
                print(f"     ❌ 失败: {str(e)}")
                continue

        print(f"\n  小结: {source} 上传完成（成功 {uploaded_count}/{len(image_files)}）")
    
    return results

def fetch_macaulay_attribution(asset_id):
    """
    从 Macaulay Library 获取署名信息（仅在需要时调用）
    
    Args:
        asset_id: Macaulay asset ID
    
    Returns:
        dict: 署名信息，或 None
    """
    if requests is None:
        return None  # requests 未安装，跳过
    
    try:
        page_url = f"https://macaulaylibrary.org/asset/{asset_id}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        
        response = requests.get(page_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            html = response.text
            
            # 提取摄影师名称
            photographer_match = re.search(r'userDisplayName["\']?\s*:\s*["\']([^"\']+)["\']', html)
            species_match = re.search(r'commonName["\']?\s*:\s*["\']([^"\']+)["\']', html)
            
            if photographer_match:
                photographer = photographer_match.group(1)
                species = species_match.group(1) if species_match else "Bird"
                
                return {
                    'photographer': photographer,
                    'photographer_url': f"https://macaulaylibrary.org/asset/{asset_id}",
                    'license': '© Cornell Lab of Ornithology (non-commercial use)',
                    'license_url': 'https://support.ebird.org/en/support/solutions/articles/48001064570',
                    'credit_format': f"{species} by {photographer}; Cornell Lab of Ornithology | Macaulay Library",
                    'source': 'macaulay',
                    'source_id': asset_id,
                    'note': None
                }
        
        return None
        
    except Exception:
        # 如果获取失败，返回 None（不影响上传流程）
        return None

def find_attribution_for_file(filename, source, download_metadata):
    """
    从下载元数据中查找文件对应的署名信息
    
    Args:
        filename: 文件名
        source: 来源（macaulay, inaturalist等）
        download_metadata: 下载元数据字典
    
    Returns:
        dict: 署名信息
    """
    # 默认空署名
    attribution = {
        'photographer': None,
        'photographer_url': None,
        'license': None,
        'license_url': None,
        'credit_format': None,
        'source': source,
        'source_id': None,
        'note': '署名信息待补充'
    }
    
    # 如果有下载元数据，尝试匹配
    if download_metadata and source in download_metadata:
        source_meta = download_metadata[source]
        for meta in source_meta:
            if meta.get('filename') == filename:
                # 合并元数据
                attribution.update({
                    'photographer': meta.get('photographer'),
                    'photographer_url': meta.get('photographer_url') or meta.get('observation_url') or meta.get('asset_url') or meta.get('commons_url'),
                    'license': meta.get('license'),
                    'license_url': meta.get('license_url'),
                    'credit_format': meta.get('credit_format'),
                    'source_id': meta.get('asset_id') or meta.get('observation_id') or meta.get('photo_id') or meta.get('flickr_photo_id'),
                    'note': meta.get('note')
                })
                break
    
        # 如果是 Macaulay 且没有完整署名信息，尝试获取
        if source == 'macaulay' and not attribution.get('photographer'):
            asset_id = attribution.get('source_id')
            if not asset_id:
                # 尝试从文件名提取 asset_id（格式：slug_ASSET_ID.jpg）
                match = re.search(r'_(\d+)\.jpg$', filename)
                if match:
                    asset_id = match.group(1)
            
            if asset_id:
                print(f"     📥 获取 Macaulay 署名信息 (Asset {asset_id})...")
                macaulay_attr = fetch_macaulay_attribution(asset_id)
                if macaulay_attr:
                    attribution.update(macaulay_attr)
                    print(f"     ✅ 已获取署名: {macaulay_attr.get('photographer')}")
                else:
                    print(f"     ⚠️  未能获取署名信息")
    
    return attribution

def generate_summary(bird_name, results):
    """生成上传摘要"""
    print(f"\n{'='*60}")
    print(f"上传完成摘要: {bird_name}")
    print(f"{'='*60}\n")
    
    total = 0
    for source, images in results.items():
        # 跳过 bird_info 字段（它是字典，不是图片列表）
        if source == 'bird_info' or not isinstance(images, list):
            continue
        count = len(images)
        if count > 0:
            print(f"  {source:15} {count} 张图片")
            total += count
    
    print(f"\n  {'总计':15} {total} 张图片")
    print(f"\n{'='*60}\n")
    
    return total

def save_results_to_file(bird_name, results):
    """保存结果到JSON文件"""
    import json
    
    output_dir = Path("cloudinary_uploads")
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / f"{bird_name}_cloudinary_urls.json"
    
    # 如果文件已存在，读取现有数据以保留额外字段（如sounds）
    existing_data = {}
    if output_file.exists():
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except:
            pass
    
    # 确保 bird_info 在最前面（如果存在）
    ordered_results = {}
    if 'bird_info' in results:
        ordered_results['bird_info'] = results['bird_info']
    
    for key in ['macaulay', 'inaturalist', 'birdphotos', 'wikimedia', 'avibase']:
        if key in results:
            ordered_results[key] = results[key]
    
    # 保留现有的额外字段（如sounds、其他未来可能添加的字段）
    for key in existing_data:
        if key not in ordered_results and key not in ['macaulay', 'inaturalist', 'birdphotos', 'wikimedia', 'avibase', 'bird_info']:
            ordered_results[key] = existing_data[key]
            print(f"   ℹ️  保留额外字段: {key}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ordered_results, f, indent=2, ensure_ascii=False)
    
    print(f"📄 URL信息已保存到: {output_file}")
    
    return output_file

def load_bird_info_from_csv(bird_name):
    """从 all_birds.csv 加载鸟类信息"""
    import csv
    csv_file = Path('all_birds.csv')
    
    if not csv_file.exists():
        return None
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # 跳过注释行，找到实际数据行
            data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
            
            # 检查是否有chinese_name字段
            header_line = None
            for i, line in enumerate(lines):
                if line.strip().startswith('#'):
                    header_line = i
                    break
            
            has_chinese = False
            if header_line is not None:
                header = lines[header_line].strip()
                has_chinese = 'chinese_name' in header.lower()
            
            if data_lines:
                # 根据字段选择不同的fieldnames
                if has_chinese:
                    reader = csv.DictReader(data_lines, fieldnames=['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'])
                else:
                    reader = csv.DictReader(data_lines, fieldnames=['slug', 'english_name', 'scientific_name', 'wikipedia_page'])
                
                for row in reader:
                    if row.get('slug', '').strip() == bird_name:
                        return {
                            'chinese_name': row.get('chinese_name', '').strip('"') if has_chinese else '',
                            'english_name': row.get('english_name', '').strip('"'),
                            'scientific_name': row.get('scientific_name', '').strip('"')
                        }
    except Exception:
        pass
    
    return None

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python3 upload_to_cloudinary.py <bird_name> [chinese_name] [english_name] [scientific_name]")
        print("示例: python3 upload_to_cloudinary.py marsh_tit 沼泽山雀 'Marsh Tit' 'Poecile palustris'")
        print("     python3 upload_to_cloudinary.py bluetail  # 自动从all_birds.csv读取信息")
        print("     python3 upload_to_cloudinary.py all  # 上传所有鸟类")
        sys.exit(1)
    
    bird_name = sys.argv[1]
    base_path = Path("images")
    
    # 解析可选的鸟类信息参数
    bird_info = None
    if len(sys.argv) >= 5:
        # 从命令行参数获取
        bird_info = {
            'chinese_name': sys.argv[2],
            'english_name': sys.argv[3],
            'scientific_name': sys.argv[4]
        }
    else:
        # 尝试从all_birds.csv自动读取
        bird_info = load_bird_info_from_csv(bird_name)
        if bird_info:
            print(f"📋 从 all_birds.csv 读取鸟类信息: {bird_info.get('chinese_name')} / {bird_info.get('english_name')}")
    
    if bird_name == "all":
        # 上传所有鸟类
        bird_dirs = [d.name for d in base_path.iterdir() if d.is_dir()]
        print(f"\n找到 {len(bird_dirs)} 个鸟类目录: {', '.join(bird_dirs)}\n")
        
        all_results = {}
        for bird in bird_dirs:
            # 为每个鸟类尝试从CSV加载信息
            bird_info = load_bird_info_from_csv(bird)
            results = upload_bird_images(bird, base_path, bird_info)
            all_results[bird] = results
            generate_summary(bird, results)
            save_results_to_file(bird, results)
        
        print(f"\n🎉 所有鸟类上传完成！")
        
    else:
        # 上传单个鸟类
        results = upload_bird_images(bird_name, base_path, bird_info)
        total = generate_summary(bird_name, results)
        
        if total > 0:
            save_results_to_file(bird_name, results)
            if bird_info:
                print(f"\n🎉 上传完成！{total} 张图片已上传到Cloudinary")
                print(f"📝 鸟类信息: {bird_info['chinese_name']} / {bird_info['english_name']}")
            else:
                print(f"\n🎉 上传完成！{total} 张图片已上传到Cloudinary")
                print(f"⚠️  提示: 未提供鸟类信息，JSON文件中可能缺少bird_info字段")
        else:
            print(f"\n⚠️  没有上传任何图片")

if __name__ == "__main__":
    main()
