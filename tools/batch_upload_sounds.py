#!/usr/bin/env python3
"""
批量上传鸟类叫声到Cloudinary并更新JSON
"""

import os
import sys
import json
import re
import cloudinary
import cloudinary.uploader
from pathlib import Path

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

def upload_sound_to_cloudinary(bird_slug, sound_file_path):
    """
    上传单个音频文件到Cloudinary
    """
    sound_path = Path(sound_file_path)
    
    if not sound_path.exists():
        print(f"  ❌ 文件不存在: {sound_path}")
        return None
    
    try:
        # 构建Cloudinary路径
        folder = f"bird-gallery/{bird_slug}/sounds"
        public_id = sound_path.stem
        
        print(f"  📤 上传中...")
        
        # 上传到Cloudinary（添加90秒超时，声音文件可能较大）
        result = cloudinary.uploader.upload(
            str(sound_path),
            folder=folder,
            public_id=public_id,
            overwrite=True,
            resource_type="video",
            format=sound_path.suffix[1:],
            timeout=90
        )
        
        # 构建音频信息
        sound_info = {
            'original_file': sound_path.name,
            'url': result['secure_url'],
            'public_id': result['public_id'],
            'duration': result.get('duration'),
            'format': result['format'],
            'bytes': result['bytes'],
            'bit_rate': result.get('bit_rate'),
            'audio_codec': result.get('audio', {}).get('codec') if 'audio' in result else None,
            'audio_frequency': result.get('audio', {}).get('frequency') if 'audio' in result else None
        }
        
        # 从文件名提取asset_id
        match = re.search(r'_(\d+)\.(mp3|wav|ogg|m4a)$', sound_path.name)
        if match:
            asset_id = match.group(1)
            sound_info['attribution'] = {
                'recordist': 'Unknown',
                'source': 'macaulay',
                'source_id': asset_id,
                'asset_url': f"https://macaulaylibrary.org/asset/{asset_id}",
                'license': '© Cornell Lab of Ornithology (non-commercial use)',
                'license_url': 'https://support.ebird.org/en/support/solutions/articles/48001064570',
                'note': None
            }
        else:
            sound_info['attribution'] = {
                'recordist': None,
                'source': None,
                'source_id': None,
                'asset_url': None,
                'license': None,
                'license_url': None,
                'note': '署名信息待补充'
            }
        
        size_kb = result['bytes'] / 1024
        duration_str = f"{sound_info['duration']:.1f}秒" if sound_info['duration'] else "未知"
        
        print(f"  ✅ 上传成功 ({size_kb:.1f}KB, {duration_str})")
        
        return sound_info
        
    except Exception as e:
        print(f"  ❌ 上传失败: {str(e)}")
        return None

def update_json_with_sound(bird_slug, sound_info, json_path):
    """
    更新指定路径的JSON文件，添加音频信息
    """
    json_file = Path(json_path)
    
    if not json_file.exists():
        print(f"    ⚠️  JSON不存在: {json_file}")
        return False
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"    ❌ 读取JSON失败: {e}")
        return False
    
    # 添加或更新sounds字段
    if 'sounds' not in data:
        data['sounds'] = []
    
    # 检查是否已存在
    existing = False
    for i, sound in enumerate(data['sounds']):
        if sound.get('original_file') == sound_info['original_file']:
            data['sounds'][i] = sound_info
            existing = True
            break
    
    if not existing:
        data['sounds'].append(sound_info)
    
    # 保存
    try:
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"    ❌ 保存JSON失败: {e}")
        return False

def batch_upload_and_update(download_record_file):
    """
    批量上传音频并更新所有相关JSON文件
    """
    # 读取下载记录
    with open(download_record_file, 'r', encoding='utf-8') as f:
        record = json.load(f)
    
    downloaded_files = record.get('downloaded_files', {})
    
    print(f"\n{'='*70}")
    print(f"批量上传鸟类叫声到Cloudinary")
    print(f"总数: {len(downloaded_files)} 个音频文件")
    print(f"{'='*70}\n")
    
    success_count = 0
    update_count = 0
    
    for i, (slug, file_path) in enumerate(downloaded_files.items(), 1):
        print(f"\n[{i}/{len(downloaded_files)}] {slug}")
        
        # 1. 上传到Cloudinary
        sound_info = upload_sound_to_cloudinary(slug, file_path)
        
        if not sound_info:
            continue
        
        success_count += 1
        
        # 2. 更新主目录的JSON
        main_json = Path(f"cloudinary_uploads/{slug}_cloudinary_urls.json")
        if main_json.exists():
            if update_json_with_sound(slug, sound_info, main_json):
                print(f"  ✅ 已更新主JSON: {main_json.name}")
                update_count += 1
            else:
                print(f"  ⚠️  主JSON更新失败")
        else:
            print(f"  ⚠️  主JSON不存在（将跳过）")
        
        # 3. 更新location_birds目录下的JSON
        location_json = Path(f"feather-flash-quiz/location_birds/新手必看家附近就有/000000/{slug}_cloudinary_urls.json")
        if location_json.exists():
            if update_json_with_sound(slug, sound_info, location_json):
                print(f"  ✅ 已更新location JSON")
                update_count += 1
            else:
                print(f"  ⚠️  location JSON更新失败")
        else:
            print(f"  ⚠️  location JSON不存在")
    
    # 打印总结
    print(f"\n{'='*70}")
    print(f"上传和更新完成")
    print(f"{'='*70}")
    print(f"✅ 上传成功: {success_count}/{len(downloaded_files)}")
    print(f"📝 JSON更新数: {update_count}")
    print(f"{'='*70}\n")

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python3 batch_upload_sounds.py <download_record.json>")
        print("示例: python3 batch_upload_sounds.py sounds_download/download_record.json")
        sys.exit(1)
    
    record_file = sys.argv[1]
    
    if not Path(record_file).exists():
        print(f"❌ 文件不存在: {record_file}")
        sys.exit(1)
    
    batch_upload_and_update(record_file)

if __name__ == '__main__':
    main()

