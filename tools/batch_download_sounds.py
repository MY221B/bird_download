#!/usr/bin/env python3
"""
批量下载鸟类叫声
基于test_fetch_bird_sounds.py改造
"""

import os
import sys
import json
import subprocess
import urllib.parse
from pathlib import Path

def get_ebird_code(scientific_name, english_name, ebird_token=None):
    """
    获取 eBird species code
    使用 curl 避免 SSL 证书问题
    """
    if not ebird_token:
        ebird_token = os.environ.get('EBIRD_TOKEN')
    
    if not ebird_token:
        print("⚠️  警告: 未设置 EBIRD_TOKEN 环境变量")
        return None
    
    # 先尝试用学名查询
    enc_sci_name = urllib.parse.quote(scientific_name)
    url = f"https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&locale=en&species={enc_sci_name}"
    
    try:
        result = subprocess.run(
            ['curl', '-s', '-H', f'X-eBirdApiToken: {ebird_token}', url],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            if data and len(data) > 0:
                code = data[0].get('speciesCode')
                if code:
                    return code
    except Exception as e:
        print(f"⚠️  eBird API 调用失败: {e}")
    
    return None

def search_macaulay_sounds(taxon_code, count=5):
    """
    在 Macaulay Library 搜索鸟类叫声
    """
    url = f"https://search.macaulaylibrary.org/api/v1/search?taxonCode={taxon_code}&mediaType=a&sort=rating_rank_desc&count={count}"
    
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
            
            if not results:
                return []
            
            audio_list = []
            for item in results:
                asset_id = item.get('assetId') or item.get('catalogId')
                if asset_id:
                    media_url = item.get('mediaUrl', '')
                    if not media_url:
                        media_url = f"https://cdn.download.ams.birds.cornell.edu/api/v1/asset/{asset_id}/audio"
                    
                    audio_info = {
                        'asset_id': asset_id,
                        'rating': item.get('rating', 0),
                        'duration': item.get('duration'),
                        'recordist': item.get('userDisplayName', 'Unknown'),
                        'location': item.get('locationLine2', ''),
                        'date': item.get('obsDttm', ''),
                        'behaviors': item.get('behaviors', ''),
                        'url': f"https://macaulaylibrary.org/asset/{asset_id}",
                        'media_url': media_url
                    }
                    audio_list.append(audio_info)
            
            return audio_list
    
    except Exception as e:
        print(f"❌ Macaulay API 调用失败: {e}")
        return []

def download_audio(asset_id, output_path, media_url=None):
    """
    下载 Macaulay 音频文件
    """
    if media_url:
        urls_to_try = [media_url]
    else:
        urls_to_try = [
            f"https://cdn.download.ams.birds.cornell.edu/api/v1/asset/{asset_id}/audio",
        ]
    
    for url in urls_to_try:
        try:
            result = subprocess.run(
                ['curl', '-s', '-L', '-o', str(output_path), url],
                capture_output=True,
                timeout=30
            )
            
            if result.returncode == 0 and output_path.exists():
                # 检查文件类型
                file_result = subprocess.run(
                    ['file', str(output_path)],
                    capture_output=True,
                    text=True
                )
                
                file_type = file_result.stdout.lower()
                
                # 检查是否是有效的音频文件
                if any(keyword in file_type for keyword in ['audio', 'mpeg', 'mp3', 'wav', 'ogg', 'flac', 'm4a']):
                    file_size = output_path.stat().st_size
                    
                    # 如果文件没有扩展名或扩展名错误，根据文件类型重命名
                    if 'mpeg' in file_type or 'mp3' in file_type:
                        new_path = output_path.with_suffix('.mp3')
                        if new_path != output_path:
                            output_path.rename(new_path)
                            return new_path
                    
                    return output_path
                else:
                    output_path.unlink()
            
        except Exception as e:
            if output_path.exists():
                output_path.unlink()
    
    return None

def download_bird_sound(bird_info, output_dir):
    """
    下载单个鸟类的叫声
    
    Returns:
        Path or None: 下载的音频文件路径
    """
    slug = bird_info['slug']
    english_name = bird_info['english_name']
    scientific_name = bird_info['scientific_name']
    chinese_name = bird_info.get('chinese_name', slug)
    
    print(f"\n{'='*70}")
    print(f"🐦 {chinese_name} ({english_name})")
    print(f"{'='*70}")
    
    # 1. 获取 eBird code
    ebird_code = get_ebird_code(scientific_name, english_name)
    
    if not ebird_code:
        print(f"❌ 无法获取 eBird code")
        return None
    
    print(f"✅ eBird code: {ebird_code}")
    
    # 2. 搜索音频
    audio_list = search_macaulay_sounds(ebird_code, count=5)
    
    if not audio_list:
        print(f"❌ 没有找到音频资源")
        return None
    
    print(f"✅ 找到 {len(audio_list)} 个音频资源")
    
    # 3. 下载第一个(最高评分)音频
    best_audio = audio_list[0]
    rating = best_audio['rating']
    rating_str = f"{float(rating):.2f}" if rating else "N/A"
    print(f"📥 下载最高评分的音频 (Asset ID: {best_audio['asset_id']}, 评分: {rating_str})")
    
    output_path = output_dir / f"{slug}_{best_audio['asset_id']}.mp3"
    
    downloaded_path = download_audio(best_audio['asset_id'], output_path, best_audio.get('media_url'))
    
    if downloaded_path:
        file_size = downloaded_path.stat().st_size / 1024
        print(f"✅ 下载成功: {downloaded_path.name} ({file_size:.1f} KB)")
        return downloaded_path
    else:
        print(f"❌ 下载失败")
        return None

def batch_download(birds_file, output_dir):
    """
    批量下载鸟类叫声
    """
    # 读取鸟类列表
    with open(birds_file, 'r', encoding='utf-8') as f:
        birds = json.load(f)
    
    print(f"\n{'='*70}")
    print(f"批量下载鸟类叫声")
    print(f"总数: {len(birds)} 种")
    print(f"{'='*70}\n")
    
    # 创建输出目录
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    # 下载统计
    success_count = 0
    failed_birds = []
    downloaded_files = {}
    
    for i, bird in enumerate(birds, 1):
        print(f"\n[{i}/{len(birds)}] 处理: {bird.get('chinese_name', bird['slug'])}")
        
        try:
            downloaded_path = download_bird_sound(bird, output_dir)
            if downloaded_path:
                success_count += 1
                downloaded_files[bird['slug']] = str(downloaded_path)
            else:
                failed_birds.append(bird)
        except KeyboardInterrupt:
            print("\n\n⚠️  用户中断")
            break
        except Exception as e:
            print(f"❌ 错误: {e}")
            failed_birds.append(bird)
    
    # 保存下载记录
    record = {
        'total': len(birds),
        'success': success_count,
        'failed': len(failed_birds),
        'downloaded_files': downloaded_files,
        'failed_birds': [{'slug': b['slug'], 'chinese_name': b.get('chinese_name')} for b in failed_birds]
    }
    
    record_file = output_dir / 'download_record.json'
    with open(record_file, 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    
    # 打印总结
    print(f"\n{'='*70}")
    print(f"下载完成总结")
    print(f"{'='*70}")
    print(f"✅ 成功: {success_count}/{len(birds)}")
    print(f"❌ 失败: {len(failed_birds)}/{len(birds)}")
    
    if failed_birds:
        print(f"\n失败的鸟类:")
        for bird in failed_birds:
            print(f"  - {bird.get('chinese_name', bird['slug'])} ({bird['slug']})")
    
    print(f"\n下载记录已保存到: {record_file}")
    
    return downloaded_files

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python3 batch_download_sounds.py <birds_json_file> [output_dir]")
        print("示例: python3 batch_download_sounds.py tmp_birds_to_download.json sounds_download")
        sys.exit(1)
    
    birds_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "sounds_download"
    
    if not Path(birds_file).exists():
        print(f"❌ 文件不存在: {birds_file}")
        sys.exit(1)
    
    batch_download(birds_file, output_dir)

if __name__ == '__main__':
    main()

