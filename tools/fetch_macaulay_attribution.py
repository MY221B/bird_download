#!/usr/bin/env python3
"""
为 Macaulay Library 照片补充署名信息
基于文件名中的 asset ID 从网页抓取摄影师信息
"""

import json
import requests
import re
import time
from pathlib import Path

def extract_asset_id(filename):
    """从文件名提取 asset ID"""
    # 格式: bird_name_ASSETID.jpg
    match = re.search(r'_(\d{6,})\.jpg$', filename)
    if match:
        return match.group(1)
    return None

def fetch_macaulay_attribution(asset_id):
    """从 Macaulay Library 获取署名信息"""
    try:
        page_url = f"https://macaulaylibrary.org/asset/{asset_id}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        
        response = requests.get(page_url, headers=headers, timeout=15)
        
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
        
    except Exception as e:
        print(f"      ⚠️  错误: {e}")
        return None

def update_cloudinary_json(json_file):
    """更新单个 cloudinary JSON 文件的 Macaulay 署名"""
    print(f"\n处理: {json_file.name}")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if 'macaulay' not in data or not data['macaulay']:
        print(f"   ⏭️  无 Macaulay 照片")
        return 0
    
    updated_count = 0
    
    for image in data['macaulay']:
        filename = image.get('original_file', '')
        asset_id = extract_asset_id(filename)
        
        if not asset_id:
            print(f"   ⚠️  无法提取 asset ID: {filename}")
            continue
        
        # 检查是否已有署名信息
        if image.get('attribution', {}).get('photographer'):
            print(f"   ⏭️  已有署名: {filename}")
            continue
        
        print(f"   📥 获取署名: {filename} (Asset {asset_id})")
        
        attribution = fetch_macaulay_attribution(asset_id)
        
        if attribution:
            image['attribution'] = attribution
            print(f"      ✅ {attribution['photographer']}")
            updated_count += 1
        else:
            print(f"      ❌ 获取失败")
        
        # 避免请求过快
        time.sleep(1)
    
    if updated_count > 0:
        # 保存更新
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"   💾 已保存: {updated_count} 张照片的署名信息")
    
    return updated_count

def main():
    """主函数"""
    print("="*70)
    print("为 Macaulay Library 照片补充署名信息")
    print("="*70)
    
    cloudinary_dir = Path("/Users/my/Desktop/Code/小鸟记忆卡/cloudinary_uploads")
    
    if not cloudinary_dir.exists():
        print(f"❌ 目录不存在: {cloudinary_dir}")
        return
    
    json_files = sorted(cloudinary_dir.glob("*_cloudinary_urls.json"))
    
    if not json_files:
        print(f"⚠️  未找到 JSON 文件")
        return
    
    print(f"\n找到 {len(json_files)} 个文件")
    print("开始获取署名信息...\n")
    
    total_updated = 0
    total_files = 0
    
    for json_file in json_files:
        count = update_cloudinary_json(json_file)
        if count > 0:
            total_updated += count
            total_files += 1
    
    print("\n" + "="*70)
    print(f"✅ 完成！")
    print(f"   处理文件: {len(json_files)} 个")
    print(f"   更新文件: {total_files} 个")
    print(f"   更新照片: {total_updated} 张")
    print("="*70)

if __name__ == "__main__":
    main()

