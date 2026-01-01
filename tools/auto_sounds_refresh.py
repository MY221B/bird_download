#!/usr/bin/env python3
"""
自动检查和下载缺失的鸟叫声
集成到weekly refresh流程中使用
"""

import json
import os
import re
import subprocess
import urllib.parse
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import cloudinary
import cloudinary.uploader

# Cloudinary配置
CLOUD_NAME = "dzor6lhz8"
API_KEY = "972579995456539"
API_SECRET = "pKXHi4_VR4fasuJ0AanitLGWfCM"

cloudinary.config(
    cloud_name=CLOUD_NAME,
    api_key=API_KEY,
    api_secret=API_SECRET,
    secure=True
)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def check_missing_sounds(bird_slugs: List[str]) -> Tuple[List[str], List[str]]:
    """
    检查哪些鸟类缺少叫声
    
    Returns:
        (missing_slugs, has_sounds_slugs): 缺少叫声的和已有叫声的slug列表
    """
    missing = []
    has_sounds = []
    
    for slug in bird_slugs:
        json_file = PROJECT_ROOT / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
        
        if not json_file.exists():
            # 如果连JSON都没有，优先处理图片，暂不处理声音
            continue
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查是否有sounds字段且非空
            sounds = data.get('sounds', [])
            if sounds and len(sounds) > 0:
                has_sounds.append(slug)
            else:
                missing.append(slug)
        except Exception as e:
            print(f"  ⚠️  {slug}: 读取JSON失败 - {e}")
            missing.append(slug)
    
    return missing, has_sounds


def get_bird_info_from_json(slug: str) -> Optional[Dict[str, str]]:
    """从JSON文件获取鸟类信息"""
    json_file = PROJECT_ROOT / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
    
    if not json_file.exists():
        return None
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        bird_info = data.get('bird_info', {})
        return {
            'slug': slug,
            'chinese_name': bird_info.get('chinese_name', ''),
            'english_name': bird_info.get('english_name', ''),
            'scientific_name': bird_info.get('scientific_name', '')
        }
    except:
        return None


def get_ebird_code(scientific_name: str, english_name: str) -> Optional[str]:
    """获取eBird species code"""
    ebird_token = os.environ.get('EBIRD_TOKEN')
    
    if not ebird_token:
        return None
    
    try:
        enc_sci_name = urllib.parse.quote(scientific_name)
        url = f"https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&locale=en&species={enc_sci_name}"
        
        result = subprocess.run(
            ['curl', '-s', '-H', f'X-eBirdApiToken: {ebird_token}', url],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            if data and len(data) > 0:
                return data[0].get('speciesCode')
    except:
        pass
    
    return None


def search_macaulay_sounds(taxon_code: str) -> Optional[Dict]:
    """搜索Macaulay音频"""
    url = f"https://search.macaulaylibrary.org/api/v1/search?taxonCode={taxon_code}&mediaType=a&sort=rating_rank_desc&count=3"
    
    try:
        result = subprocess.run(
            ['curl', '-s', '-H', 'Accept: application/json', '-H', 'User-Agent: Mozilla/5.0', url],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            results = data.get('results', {}).get('content', [])
            
            if results:
                item = results[0]  # 取评分最高的
                asset_id = item.get('assetId') or item.get('catalogId')
                if asset_id:
                    media_url = item.get('mediaUrl', '')
                    if not media_url:
                        media_url = f"https://cdn.download.ams.birds.cornell.edu/api/v1/asset/{asset_id}/audio"
                    
                    return {
                        'asset_id': asset_id,
                        'rating': item.get('rating', 0),
                        'duration': item.get('duration'),
                        'media_url': media_url
                    }
    except:
        pass
    
    return None


def download_sound(asset_id: str, output_dir: Path, slug: str) -> Optional[Path]:
    """下载音频文件"""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slug}_{asset_id}.mp3"
    
    url = f"https://cdn.download.ams.birds.cornell.edu/api/v1/asset/{asset_id}/audio"
    
    try:
        result = subprocess.run(
            ['curl', '-s', '-L', '-o', str(output_path), url],
            capture_output=True,
            timeout=30
        )
        
        if result.returncode == 0 and output_path.exists():
            # 验证是否为音频文件
            file_result = subprocess.run(
                ['file', str(output_path)],
                capture_output=True,
                text=True
            )
            
            if any(kw in file_result.stdout.lower() for kw in ['audio', 'mpeg', 'mp3']):
                return output_path
            else:
                output_path.unlink()
    except:
        if output_path.exists():
            output_path.unlink()
    
    return None


def upload_sound_to_cloudinary(slug: str, sound_path: Path) -> Optional[Dict]:
    """上传音频到Cloudinary"""
    try:
        folder = f"bird-gallery/{slug}/sounds"
        public_id = sound_path.stem
        
        result = cloudinary.uploader.upload(
            str(sound_path),
            folder=folder,
            public_id=public_id,
            overwrite=True,
            resource_type="video",
            format=sound_path.suffix[1:]
        )
        
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
        
        return sound_info
    except Exception as e:
        print(f"    ❌ Cloudinary上传失败: {e}")
        return None


def update_json_with_sound(slug: str, sound_info: Dict) -> bool:
    """更新JSON文件添加sounds字段"""
    json_file = PROJECT_ROOT / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
    
    if not json_file.exists():
        return False
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
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
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"    ❌ JSON更新失败: {e}")
        return False


def download_and_upload_sounds(
    bird_slugs: List[str],
    temp_dir: Path,
    max_attempts: int = 2
) -> Tuple[List[str], List[Dict]]:
    """
    批量下载和上传鸟叫声
    
    Returns:
        (success_slugs, failed_birds): 成功的slug列表和失败的详细信息
    """
    print("\n" + "=" * 80)
    print("🎵 检查和下载鸟叫声")
    print("=" * 80)
    
    # 检查缺失的叫声
    missing_slugs, has_sounds_slugs = check_missing_sounds(bird_slugs)
    
    print(f"\n📊 叫声状态:")
    print(f"  ✅ 已有叫声: {len(has_sounds_slugs)} 种")
    print(f"  ⏳ 需要下载: {len(missing_slugs)} 种")
    
    if not missing_slugs:
        print("\n✨ 所有鸟类都已有叫声，无需下载")
        return [], []
    
    # 显示前几个需要下载的
    if len(missing_slugs) <= 10:
        print(f"\n需要下载的鸟类:")
        for slug in missing_slugs:
            info = get_bird_info_from_json(slug)
            if info:
                name = info.get('chinese_name') or info.get('english_name') or slug
                print(f"  - {name} ({slug})")
    else:
        print(f"\n需要下载的鸟类（前10个）:")
        for slug in missing_slugs[:10]:
            info = get_bird_info_from_json(slug)
            if info:
                name = info.get('chinese_name') or info.get('english_name') or slug
                print(f"  - {name} ({slug})")
        print(f"  ... 还有 {len(missing_slugs) - 10} 个")
    
    # 创建临时目录
    sounds_dir = temp_dir / "sounds_download"
    sounds_dir.mkdir(parents=True, exist_ok=True)
    
    success_slugs = []
    failed_birds = []
    
    for i, slug in enumerate(missing_slugs, 1):
        print(f"\n[{i}/{len(missing_slugs)}] {slug}")
        
        # 获取鸟类信息
        info = get_bird_info_from_json(slug)
        if not info:
            print(f"  ⚠️  无法获取鸟类信息，跳过")
            failed_birds.append({
                'slug': slug,
                'reason': '无法获取鸟类信息',
                'chinese_name': slug
            })
            continue
        
        chinese_name = info.get('chinese_name', '')
        english_name = info.get('english_name', '')
        scientific_name = info.get('scientific_name', '')
        
        if not scientific_name:
            print(f"  ⚠️  缺少学名，跳过")
            failed_birds.append({
                'slug': slug,
                'reason': '缺少学名',
                'chinese_name': chinese_name or english_name
            })
            continue
        
        print(f"  {chinese_name or english_name}")
        
        # 获取eBird code
        ebird_code = get_ebird_code(scientific_name, english_name)
        if not ebird_code:
            print(f"  ⚠️  无法获取eBird code（可能eBird数据库中无此物种）")
            failed_birds.append({
                'slug': slug,
                'reason': 'eBird数据库中无此物种',
                'chinese_name': chinese_name or english_name
            })
            continue
        
        print(f"  ✓ eBird code: {ebird_code}")
        
        # 搜索音频
        audio_info = search_macaulay_sounds(ebird_code)
        if not audio_info:
            print(f"  ⚠️  Macaulay Library中找不到音频")
            failed_birds.append({
                'slug': slug,
                'reason': 'Macaulay Library中找不到音频',
                'chinese_name': chinese_name or english_name
            })
            continue
        
        print(f"  ✓ 找到音频 (Asset: {audio_info['asset_id']}, 评分: {audio_info.get('rating', 'N/A')})")
        
        # 下载音频
        sound_path = download_sound(audio_info['asset_id'], sounds_dir, slug)
        if not sound_path:
            print(f"  ❌ 下载失败")
            failed_birds.append({
                'slug': slug,
                'reason': '音频下载失败',
                'chinese_name': chinese_name or english_name
            })
            continue
        
        file_size = sound_path.stat().st_size / 1024
        print(f"  ✓ 已下载 ({file_size:.1f}KB)")
        
        # 上传到Cloudinary
        sound_info = upload_sound_to_cloudinary(slug, sound_path)
        if not sound_info:
            print(f"  ❌ Cloudinary上传失败")
            failed_birds.append({
                'slug': slug,
                'reason': 'Cloudinary上传失败',
                'chinese_name': chinese_name or english_name
            })
            continue
        
        print(f"  ✓ 已上传到Cloudinary")
        
        # 更新JSON
        if update_json_with_sound(slug, sound_info):
            print(f"  ✓ 已更新JSON")
            success_slugs.append(slug)
        else:
            print(f"  ⚠️  JSON更新失败（但音频已上传）")
            failed_birds.append({
                'slug': slug,
                'reason': 'JSON更新失败',
                'chinese_name': chinese_name or english_name
            })
    
    return success_slugs, failed_birds


def print_sounds_summary(success_slugs: List[str], failed_birds: List[Dict]):
    """打印叫声下载总结"""
    print("\n" + "=" * 80)
    print("🎵 叫声下载总结")
    print("=" * 80)
    
    total = len(success_slugs) + len(failed_birds)
    if total == 0:
        print("\n✨ 所有鸟类都已有叫声")
        return
    
    print(f"\n✅ 成功: {len(success_slugs)}/{total}")
    
    if failed_birds:
        print(f"❌ 失败: {len(failed_birds)}/{total}")
        print(f"\n失败的鸟类:")
        for bird in failed_birds[:10]:
            name = bird.get('chinese_name') or bird['slug']
            reason = bird.get('reason', '未知原因')
            print(f"  - {name} ({bird['slug']}): {reason}")
        
        if len(failed_birds) > 10:
            print(f"  ... 还有 {len(failed_birds) - 10} 个")
    
    print("=" * 80)


if __name__ == '__main__':
    # 测试用
    import sys
    if len(sys.argv) > 1:
        test_slugs = sys.argv[1:]
        temp_dir = PROJECT_ROOT / "tmp" / "test_sounds"
        success, failed = download_and_upload_sounds(test_slugs, temp_dir)
        print_sounds_summary(success, failed)














