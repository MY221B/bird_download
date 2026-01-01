#!/usr/bin/env python3
"""
优化照片的 credit_format 字段
将 "Bird by..." 替换为具体的鸟名
"""

import json
import re
from pathlib import Path

def optimize_cloudinary_json(json_file):
    """优化单个 cloudinary JSON 文件"""
    print(f"\n处理: {json_file.name}")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    updated_count = 0
    
    # 获取鸟名信息
    bird_info = data.get('bird_info', {})
    english_name = bird_info.get('english_name', '')
    
    # 处理各个来源的照片
    for source in ['macaulay', 'inaturalist', 'wikimedia', 'avibase']:
        if source in data:
            for photo in data[source]:
                attr = photo.get('attribution', {})
                credit = attr.get('credit_format', '')
                photographer = attr.get('photographer')
                
                # 如果有署名信息但格式是通用的 "Bird by..."
                if credit and photographer and 'Bird by' in credit and english_name:
                    # 替换为具体鸟名
                    new_credit = credit.replace('Bird by', f'{english_name} by')
                    
                    if new_credit != credit:
                        attr['credit_format'] = new_credit
                        updated_count += 1
                        print(f"  ✅ {photo['original_file']}: 更新引用格式")
    
    if updated_count > 0:
        # 保存
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  💾 已更新 {updated_count} 个引用格式")
    else:
        print(f"  ⏭️  无需更新")
    
    return updated_count

def main():
    """主函数"""
    print("="*70)
    print("优化照片 credit_format 字段")
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
    
    total_updated = 0
    for json_file in json_files:
        count = optimize_cloudinary_json(json_file)
        total_updated += count
    
    print("\n" + "="*70)
    print(f"✅ 完成！共更新 {total_updated} 个引用格式")
    print("="*70)

if __name__ == "__main__":
    main()

