#!/usr/bin/env python3
"""
清理 attribution.note 字段
如果已有完整署名信息，将 note 设为 null
"""

import json
from pathlib import Path

def cleanup_note_field(json_file):
    """清理 note 字段"""
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    updated_count = 0
    
    for source in ['macaulay', 'inaturalist', 'wikimedia', 'avibase']:
        if source in data:
            for photo in data[source]:
                attr = photo.get('attribution', {})
                
                # 如果有完整的署名信息，清理 note
                if attr.get('credit_format') and attr.get('credit_format') != 'null':
                    if attr.get('note') == '署名信息待补充':
                        attr['note'] = None
                        updated_count += 1
    
    if updated_count > 0:
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    return updated_count

def main():
    """主函数"""
    print("="*70)
    print("清理 note 字段")
    print("="*70)
    
    cloudinary_dir = Path("cloudinary_uploads")
    json_files = sorted(cloudinary_dir.glob("*_cloudinary_urls.json"))
    
    total_updated = 0
    for json_file in json_files:
        count = cleanup_note_field(json_file)
        total_updated += count
    
    print(f"\n✅ 完成！清理了 {total_updated} 个 note 字段")

if __name__ == "__main__":
    main()

