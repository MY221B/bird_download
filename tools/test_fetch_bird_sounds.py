#!/usr/bin/env python3
"""
测试从 Macaulay Library 下载鸟类叫声
基于现有的图片下载逻辑进行改造
"""

import os
import sys
import json
import urllib.parse
import urllib.request
import subprocess
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
                    print(f"✅ 通过学名找到 eBird code: {code}")
                    return code
    except Exception as e:
        print(f"⚠️  eBird API (学名) 调用失败: {e}")
    
    print(f"ℹ️  学名未找到，尝试用英文名查找...")
    # TODO: 可以添加用英文名从完整taxonomy查找的逻辑
    
    return None

def search_macaulay_sounds(taxon_code, count=10):
    """
    在 Macaulay Library 搜索鸟类叫声
    使用 curl 避免 SSL 证书问题
    
    参数:
        taxon_code: eBird species code
        count: 返回结果数量
    
    返回:
        包含音频资源信息的列表
    """
    # 构建搜索URL - 关键：mediaType=a 表示音频(audio)
    url = f"https://search.macaulaylibrary.org/api/v1/search?taxonCode={taxon_code}&mediaType=a&sort=rating_rank_desc&count={count}"
    
    print(f"\n🔍 搜索 Macaulay 音频:")
    print(f"   URL: {url}")
    
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
                print("❌ 没有找到音频结果")
                return []
            
            print(f"✅ 找到 {len(results)} 个音频资源")
            
            audio_list = []
            for item in results:
                asset_id = item.get('assetId') or item.get('catalogId')
                if asset_id:
                    # 从API响应中获取音频下载URL
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
    
    参数:
        asset_id: Macaulay asset ID
        output_path: 输出文件路径
        media_url: 直接的媒体URL（从API获取）
    
    返回:
        是否成功下载
    """
    # 正确的音频下载URL格式
    if media_url:
        urls_to_try = [media_url]
    else:
        urls_to_try = [
            f"https://cdn.download.ams.birds.cornell.edu/api/v1/asset/{asset_id}/audio",
        ]
    
    for url in urls_to_try:
        try:
            print(f"\n   尝试下载: {url}")
            
            # 使用 curl 下载
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
                print(f"   文件类型: {file_type}")
                
                # 检查是否是有效的音频文件
                if any(keyword in file_type for keyword in ['audio', 'mpeg', 'mp3', 'wav', 'ogg', 'flac', 'm4a']):
                    file_size = output_path.stat().st_size
                    print(f"   ✅ 成功下载音频文件 (大小: {file_size / 1024:.1f} KB)")
                    
                    # 如果文件没有扩展名或扩展名错误，根据文件类型重命名
                    if 'mpeg' in file_type or 'mp3' in file_type:
                        new_path = output_path.with_suffix('.mp3')
                        if new_path != output_path:
                            output_path.rename(new_path)
                            print(f"   📝 重命名为: {new_path.name}")
                    
                    return True
                else:
                    print(f"   ⚠️  不是音频文件")
                    output_path.unlink()
            
        except Exception as e:
            print(f"   ❌ 下载失败: {e}")
            if output_path.exists():
                output_path.unlink()
    
    print(f"   ❌ 所有URL都失败了")
    return False

def test_bird_sound(english_name, scientific_name, slug=None):
    """
    测试下载单个鸟类的叫声
    """
    print("=" * 70)
    print(f"测试下载鸟类叫声")
    print(f"  英文名: {english_name}")
    print(f"  学名: {scientific_name}")
    print("=" * 70)
    
    # 1. 获取 eBird code
    ebird_code = get_ebird_code(scientific_name, english_name)
    
    if not ebird_code:
        print("\n❌ 无法获取 eBird code，无法继续")
        return False
    
    # 2. 搜索音频
    audio_list = search_macaulay_sounds(ebird_code, count=5)
    
    if not audio_list:
        print("\n❌ 没有找到音频资源")
        return False
    
    # 3. 显示找到的音频信息
    print("\n" + "=" * 70)
    print("找到的音频资源:")
    print("=" * 70)
    for i, audio in enumerate(audio_list, 1):
        print(f"\n{i}. Asset ID: {audio['asset_id']}")
        print(f"   评分: {audio['rating']}")
        print(f"   时长: {audio['duration']}秒" if audio['duration'] else "   时长: 未知")
        print(f"   录音者: {audio['recordist']}")
        print(f"   地点: {audio['location']}")
        print(f"   日期: {audio['date']}")
        print(f"   行为: {audio['behaviors']}" if audio['behaviors'] else "")
        print(f"   网页: {audio['url']}")
    
    # 4. 下载第一个(最高评分)音频
    best_audio = audio_list[0]
    print("\n" + "=" * 70)
    print(f"下载最高评分的音频 (Asset ID: {best_audio['asset_id']})")
    print("=" * 70)
    
    # 创建测试输出目录
    output_dir = Path("test_sounds")
    output_dir.mkdir(exist_ok=True)
    
    # 使用slug或学名作为文件名
    filename = slug if slug else scientific_name.replace(' ', '_').lower()
    output_path = output_dir / f"{filename}_{best_audio['asset_id']}.mp3"
    
    success = download_audio(best_audio['asset_id'], output_path, best_audio.get('media_url'))
    
    if success:
        print(f"\n✅ 测试成功！音频已保存到: {output_path}")
        print(f"\n💡 可以用以下命令播放:")
        print(f"   afplay {output_path}")
        return True
    else:
        print(f"\n❌ 测试失败：无法下载音频")
        return False

def main():
    """主函数"""
    # 测试用例 - 使用几个常见的鸟类
    test_cases = [
        {
            'english_name': 'Red-flanked Bluetail',
            'scientific_name': 'Tarsiger cyanurus',
            'slug': 'bluetail'
        },
        {
            'english_name': 'Oriental Magpie-Robin',
            'scientific_name': 'Copsychus saularis',
            'slug': 'oriental_magpie_robin'
        },
    ]
    
    # 如果命令行提供了参数，使用命令行参数
    if len(sys.argv) >= 3:
        test_cases = [{
            'english_name': sys.argv[1],
            'scientific_name': sys.argv[2],
            'slug': sys.argv[3] if len(sys.argv) > 3 else None
        }]
    
    success_count = 0
    for test_case in test_cases:
        try:
            if test_bird_sound(**test_case):
                success_count += 1
            print("\n" + "=" * 70)
            print()
        except KeyboardInterrupt:
            print("\n\n⚠️  用户中断")
            break
        except Exception as e:
            print(f"\n❌ 错误: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n总结: {success_count}/{len(test_cases)} 个测试成功")

if __name__ == '__main__':
    main()

