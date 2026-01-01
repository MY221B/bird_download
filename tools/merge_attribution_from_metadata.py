#!/usr/bin/env python3
"""
从 download_metadata.json 合并署名信息到 cloudinary_uploads JSON
"""

import json
from pathlib import Path

def merge_attribution_from_metadata(bird_name):
    """合并署名信息"""
    # 读取 download_metadata.json
    metadata_file = Path(f"images/{bird_name}/download_metadata.json")
    
    if not metadata_file.exists():
        print(f"  ⏭️  无 download_metadata.json")
        return 0
    
    with open(metadata_file, 'r', encoding='utf-8') as f:
        download_metadata = json.load(f)
    
    # 读取 cloudinary_uploads JSON
    cloudinary_file = Path(f"cloudinary_uploads/{bird_name}_cloudinary_urls.json")
    
    if not cloudinary_file.exists():
        print(f"  ⏭️  无 cloudinary 文件")
        return 0
    
    with open(cloudinary_file, 'r', encoding='utf-8') as f:
        cloudinary_data = json.load(f)
    
    updated_count = 0
    
    # 处理各个来源
    for source in ['macaulay', 'inaturalist', 'wikimedia', 'avibase']:
        if source not in download_metadata or not download_metadata[source]:
            continue
        
        # 建立文件名索引
        metadata_index = {}
        for meta in download_metadata[source]:
            metadata_index[meta['filename']] = meta
        
        # 更新 cloudinary 照片
        if source in cloudinary_data:
            for photo in cloudinary_data[source]:
                filename = photo['original_file']
                
                # 查找对应的元数据
                if filename in metadata_index:
                    meta = metadata_index[filename]
                    attr = photo.get('attribution', {})
                    
                    # 检查是否需要更新
                    if not attr.get('credit_format') or attr['credit_format'] is None:
                        # 合并元数据
                        updated = False
                        
                        # 通用字段
                        if meta.get('photographer'):
                            attr['photographer'] = meta['photographer']
                            updated = True
                        
                        if meta.get('credit_format'):
                            attr['credit_format'] = meta['credit_format']
                            updated = True
                        
                        # 特定来源的 URL
                        if meta.get('observation_url'):
                            attr['photographer_url'] = meta['observation_url']
                            updated = True
                        elif meta.get('commons_url'):
                            attr['photographer_url'] = meta['commons_url']
                            updated = True
                        elif meta.get('flickr_url'):
                            attr['photographer_url'] = meta['flickr_url']
                            updated = True
                        
                        # 许可证
                        if meta.get('license'):
                            attr['license'] = meta['license']
                            updated = True
                        
                        if meta.get('license_url'):
                            attr['license_url'] = meta['license_url']
                            updated = True
                        
                        # source_id
                        if meta.get('observation_id'):
                            attr['source_id'] = str(meta['observation_id'])
                        elif meta.get('photo_id'):
                            attr['source_id'] = str(meta['photo_id'])
                        elif meta.get('flickr_photo_id'):
                            attr['source_id'] = str(meta['flickr_photo_id'])
                        
                        if updated:
                            updated_count += 1
    
    if updated_count > 0:
        # 保存更新
        with open(cloudinary_file, 'w', encoding='utf-8') as f:
            json.dump(cloudinary_data, f, indent=2, ensure_ascii=False)
        
        print(f"  ✅ 更新了 {updated_count} 个照片的署名")
    
    return updated_count

def main():
    """主函数"""
    print("="*70)
    print("从 download_metadata.json 合并署名信息")
    print("="*70)
    
    # 获取所有鸟种列表
    cloudinary_dir = Path("cloudinary_uploads")
    cloudinary_files = sorted(cloudinary_dir.glob("*_cloudinary_urls.json"))
    
    print(f"\n找到 {len(cloudinary_files)} 个鸟种\n")
    
    total_updated = 0
    processed = 0
    
    for cloudinary_file in cloudinary_files:
        # 提取鸟种名
        bird_name = cloudinary_file.stem.replace('_cloudinary_urls', '')
        
        print(f"处理: {bird_name}")
        
        count = merge_attribution_from_metadata(bird_name)
        
        if count > 0:
            total_updated += count
            processed += 1
    
    print("\n" + "="*70)
    print(f"✅ 完成！")
    print(f"   处理鸟种: {processed}/{len(cloudinary_files)}")
    print(f"   更新照片: {total_updated} 张")
    print("="*70)

if __name__ == "__main__":
    main()

