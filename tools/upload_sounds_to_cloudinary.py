#!/usr/bin/env python3
"""
上传鸟类叫声到Cloudinary
基于现有的图片上传脚本改造
"""

import os
import sys
import json
import cloudinary
import cloudinary.uploader
from pathlib import Path

from cloudinary_credentials import ensure_cloudinary_config


def upload_bird_sounds(bird_name, sound_file_path, base_path=None):
    """
    上传单个鸟类的叫声文件到Cloudinary
    
    Args:
        bird_name: 鸟类slug（如 'bluetail'）
        sound_file_path: 音频文件路径
        base_path: 可选的基础路径
    
    Returns:
        dict: 包含上传后的URL信息
    """
    sound_path = Path(sound_file_path)
    
    if not sound_path.exists():
        print(f"❌ 音频文件不存在: {sound_path}")
        return None

    cn = ensure_cloudinary_config()
    print(f"\n{'='*60}")
    print(f"上传鸟类叫声: {bird_name}")
    print(f"Cloudinary: cloud_name={cn}")
    print(f"音频文件: {sound_path}")
    print(f"{'='*60}\n")
    
    try:
        # 构建Cloudinary路径 - 与图片类似的结构
        folder = f"bird-gallery/{bird_name}/sounds"
        public_id = sound_path.stem  # 不含扩展名的文件名
        
        print(f"📤 上传音频文件...")
        print(f"   目标: {folder}/{public_id}")
        
        # 上传到Cloudinary - 注意resource_type为"video"（音频也用video类型）
        result = cloudinary.uploader.upload(
            str(sound_path),
            folder=folder,
            public_id=public_id,
            overwrite=True,
            resource_type="video",  # Cloudinary将音频归类为video
            # 保持原格式
            format=sound_path.suffix[1:],  # 去掉点号
            timeout=90
        )
        
        # 保存结果
        sound_info = {
            'original_file': sound_path.name,
            'url': result['secure_url'],
            'public_id': result['public_id'],
            'duration': result.get('duration'),  # 音频时长（秒）
            'format': result['format'],
            'bytes': result['bytes'],
            'bit_rate': result.get('bit_rate'),
            'audio_codec': result.get('audio', {}).get('codec') if 'audio' in result else None,
            'audio_frequency': result.get('audio', {}).get('frequency') if 'audio' in result else None
        }
        
        # 尝试从文件名中提取asset_id（格式：slug_ASSET_ID.mp3）
        import re
        match = re.search(r'_(\d+)\.(mp3|wav|ogg|m4a)$', sound_path.name)
        if match:
            asset_id = match.group(1)
            sound_info['attribution'] = {
                'recordist': 'Unknown',  # 需要从API获取
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
        
        print(f"\n✅ 上传成功!")
        print(f"   URL: {result['secure_url']}")
        print(f"   时长: {duration_str}")
        print(f"   格式: {result['format']}")
        print(f"   大小: {size_kb:.1f}KB")
        
        return sound_info
        
    except Exception as e:
        print(f"❌ 上传失败: {str(e)}")
        return None

def update_json_with_sound(bird_name, sound_info):
    """
    将音频信息添加到现有的JSON文件中
    
    Args:
        bird_name: 鸟类slug
        sound_info: 音频信息字典
    
    Returns:
        bool: 是否成功更新
    """
    json_file = Path("cloudinary_uploads") / f"{bird_name}_cloudinary_urls.json"
    
    if not json_file.exists():
        print(f"⚠️  JSON文件不存在: {json_file}")
        print(f"   将创建新文件...")
        data = {
            'macaulay': [],
            'inaturalist': [],
            'birdphotos': [],
            'wikimedia': [],
            'avibase': []
        }
    else:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"📄 读取现有JSON: {json_file}")
        except Exception as e:
            print(f"❌ 读取JSON失败: {e}")
            return False
    
    # 添加或更新sounds字段
    if 'sounds' not in data:
        data['sounds'] = []
    
    # 检查是否已存在相同的音频（根据original_file）
    existing = False
    for i, sound in enumerate(data['sounds']):
        if sound.get('original_file') == sound_info['original_file']:
            data['sounds'][i] = sound_info
            existing = True
            print(f"   ℹ️  更新已存在的音频记录")
            break
    
    if not existing:
        data['sounds'].append(sound_info)
        print(f"   ✅ 添加新音频记录")
    
    # 保存回JSON文件
    try:
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 JSON已更新: {json_file}")
        return True
    except Exception as e:
        print(f"❌ 保存JSON失败: {e}")
        return False

def main():
    """主函数"""
    if len(sys.argv) < 3:
        print("用法: python3 upload_sounds_to_cloudinary.py <bird_slug> <sound_file_path>")
        print("示例: python3 upload_sounds_to_cloudinary.py bluetail test_sounds/bluetail_134560971.mp3")
        sys.exit(1)
    
    bird_name = sys.argv[1]
    sound_file = sys.argv[2]
    
    # 上传音频
    sound_info = upload_bird_sounds(bird_name, sound_file)
    
    if sound_info:
        # 更新JSON文件
        if update_json_with_sound(bird_name, sound_info):
            print(f"\n🎉 完成！鸟叫声已上传并记录到JSON")
        else:
            print(f"\n⚠️  音频已上传，但JSON更新失败")
    else:
        print(f"\n❌ 上传失败")

if __name__ == "__main__":
    main()















