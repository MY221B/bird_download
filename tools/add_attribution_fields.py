#!/usr/bin/env python3
"""
为所有 cloudinary_uploads JSON 文件补充署名字段
保持向后兼容，为已有数据添加空的署名字段
"""

import json
from pathlib import Path

def add_attribution_to_image(image_data, source):
    """为单张图片数据添加署名字段"""
    if 'attribution' not in image_data:
        image_data['attribution'] = {
            'photographer': None,
            'photographer_url': None,
            'license': None,
            'license_url': None,
            'credit_format': None,
            'source': source,
            'source_id': None,  # asset_id, photo_id, observation_id等
            'note': '署名信息待补充'
        }
    return image_data

def process_cloudinary_json(json_file):
    """处理单个 cloudinary JSON 文件"""
    print(f"\n处理: {json_file.name}")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    updated = False
    total_images = 0
    
    # 处理各个来源
    for source in ['macaulay', 'inaturalist', 'wikimedia', 'avibase', 'birdphotos']:
        if source in data and data[source]:
            for image in data[source]:
                add_attribution_to_image(image, source)
                total_images += 1
                updated = True
    
    if updated:
        # 保存更新后的数据
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"   ✅ 已添加署名字段: {total_images} 张图片")
    else:
        print(f"   ⏭️  无需更新")
    
    return total_images

def main():
    """主函数"""
    print("="*70)
    print("为 Cloudinary 数据补充署名字段")
    print("="*70)
    
    cloudinary_dir = Path("/Users/my/Desktop/Code/小鸟记忆卡/cloudinary_uploads")
    
    if not cloudinary_dir.exists():
        print(f"❌ 目录不存在: {cloudinary_dir}")
        return
    
    json_files = list(cloudinary_dir.glob("*_cloudinary_urls.json"))
    
    if not json_files:
        print(f"⚠️  未找到 JSON 文件")
        return
    
    print(f"\n找到 {len(json_files)} 个文件")
    
    total_images = 0
    for json_file in sorted(json_files):
        count = process_cloudinary_json(json_file)
        total_images += count
    
    print("\n" + "="*70)
    print(f"✅ 完成！共处理 {len(json_files)} 个文件，{total_images} 张图片")
    print("="*70)
    
    # 显示数据结构示例
    if json_files:
        print("\n📄 数据结构示例:")
        with open(json_files[0], 'r', encoding='utf-8') as f:
            sample = json.load(f)
            for source in ['macaulay', 'inaturalist', 'wikimedia', 'avibase']:
                if source in sample and sample[source]:
                    print(f"\n{source} 字段:")
                    print(json.dumps(sample[source][0], indent=2, ensure_ascii=False))
                    break

if __name__ == "__main__":
    main()

