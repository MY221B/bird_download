#!/usr/bin/env python3
"""
批量下载缺少的 Macaulay 照片并上传到 Cloudinary
"""

import os
import sys
import csv
import subprocess
import json
from pathlib import Path

def load_bird_info_from_csv():
    """从 all_birds.csv 加载鸟类信息"""
    bird_info = {}
    csv_file = Path("all_birds.csv")
    
    if csv_file.exists():
        with open(csv_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
            if data_lines:
                reader = csv.DictReader(data_lines)
                for row in reader:
                    if 'slug' in row:
                        bird_info[row['slug']] = {
                            'english_name': row.get('english_name', '').strip('"'),
                            'scientific_name': row.get('scientific_name', '').strip('"'),
                            'wikipedia_page': row.get('wikipedia_page', '').strip('"')
                        }
    
    # 从 cloudinary_uploads JSON 文件补充信息
    cloudinary_dir = Path("cloudinary_uploads")
    if cloudinary_dir.exists():
        for json_file in cloudinary_dir.glob("*_cloudinary_urls.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'bird_info' in data:
                        info = data['bird_info']
                        slug = info.get('slug')
                        if slug and slug not in bird_info:
                            bird_info[slug] = {
                                'english_name': info.get('english_name', ''),
                                'scientific_name': info.get('scientific_name', ''),
                                'wikipedia_page': ''
                            }
            except:
                pass
    
    return bird_info

def get_missing_birds():
    """获取缺少 Macaulay 照片的鸟类列表"""
    # 运行检查脚本获取缺少的鸟类
    result = subprocess.run(
        [sys.executable, "tools/check_missing_macaulay.py"],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    
    # 读取生成的文件
    missing_file = Path("missing_macaulay_birds.txt")
    missing_birds = []
    
    if missing_file.exists():
        with open(missing_file, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 1:
                    missing_birds.append({
                        'slug': parts[0],
                        'english_name': parts[1] if len(parts) > 1 else '',
                        'scientific_name': parts[2] if len(parts) > 2 else '',
                        'wikipedia_page': parts[3] if len(parts) > 3 else ''
                    })
    
    return missing_birds

def download_macaulay_for_bird(bird, bird_info_dict):
    """为单个鸟类下载 Macaulay 照片"""
    slug = bird['slug']
    
    # 从CSV获取信息（如果存在）
    if slug in bird_info_dict:
        info = bird_info_dict[slug]
        english_name = info['english_name'] or bird.get('english_name', '')
        scientific_name = info['scientific_name'] or bird.get('scientific_name', '')
        wikipedia_page = info['wikipedia_page'] or bird.get('wikipedia_page', '')
    else:
        english_name = bird.get('english_name', '')
        scientific_name = bird.get('scientific_name', '')
        wikipedia_page = bird.get('wikipedia_page', '')
    
    # 如果没有wikipedia_page，从english_name生成
    if not wikipedia_page and english_name:
        wikipedia_page = english_name.replace(' ', '_')
    
    print(f"\n{'='*60}")
    print(f"下载 Macaulay 照片: {slug}")
    print(f"  英文名: {english_name}")
    print(f"  学名: {scientific_name}")
    print(f"{'='*60}")
    
    # 调用 fetch_four_sources.sh
    script_path = Path("tools/fetch_four_sources.sh")
    if not script_path.exists():
        print(f"❌ 脚本不存在: {script_path}")
        return False
    
    # 构建命令（只下载 Macaulay）
    # 如果 wikipedia_page 为空，则不传递该参数
    cmd = [
        "bash",
        str(script_path),
        slug,
        english_name,
        scientific_name
    ]
    
    # 如果提供了 wikipedia_page，添加到命令中
    if wikipedia_page:
        cmd.append(wikipedia_page)
    
    # 添加 --sources 参数，只下载 Macaulay
    cmd.extend(["--sources", "macaulay"])
    
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ 下载完成: {slug}")
            return True
        else:
            print(f"⚠️  下载可能有问题 (退出码: {result.returncode})")
            print(f"   输出: {result.stdout}")
            if result.stderr:
                print(f"   错误: {result.stderr}")
            # 即使有错误也继续，因为可能部分成功
            return True
    except Exception as e:
        print(f"❌ 下载失败: {e}")
        return False

def upload_to_cloudinary(bird_slug):
    """上传单个鸟类到 Cloudinary"""
    print(f"\n📤 上传到 Cloudinary: {bird_slug}")
    
    script_path = Path("tools/upload_to_cloudinary.py")
    if not script_path.exists():
        print(f"❌ 脚本不存在: {script_path}")
        return False
    
    cmd = [sys.executable, str(script_path), bird_slug]
    
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ 上传完成: {bird_slug}")
            return True
        else:
            print(f"⚠️  上传可能有问题 (退出码: {result.returncode})")
            if result.stderr:
                print(f"   错误: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ 上传失败: {e}")
        return False

def main():
    """主函数"""
    import sys
    
    # 检查是否有 --yes 参数
    auto_confirm = '--yes' in sys.argv or '-y' in sys.argv
    
    print("="*60)
    print("批量下载缺少的 Macaulay 照片并上传到 Cloudinary")
    print("="*60)
    print()
    
    # 加载鸟类信息
    print("📋 加载鸟类信息...")
    bird_info_dict = load_bird_info_from_csv()
    print(f"   从 CSV 加载了 {len(bird_info_dict)} 个鸟类信息")
    print()
    
    # 获取缺少的鸟类
    print("🔍 检查缺少 Macaulay 照片的鸟类...")
    missing_birds = get_missing_birds()
    print(f"   找到 {len(missing_birds)} 个缺少 Macaulay 照片的鸟类")
    print()
    
    if not missing_birds:
        print("✅ 所有鸟类都有 Macaulay 照片！")
        return
    
    # 确认
    print("将处理以下鸟类:")
    for bird in missing_birds:
        slug = bird['slug']
        info = bird_info_dict.get(slug, {})
        en_name = info.get('english_name') or bird.get('english_name', 'N/A')
        sci_name = info.get('scientific_name') or bird.get('scientific_name', 'N/A')
        print(f"  - {slug}: {en_name} ({sci_name})")
    print()
    
    # 询问是否继续（如果未自动确认）
    if not auto_confirm:
        try:
            response = input("是否继续下载和上传？(y/n): ").strip().lower()
            if response != 'y':
                print("已取消")
                return
        except EOFError:
            print("⚠️  检测到非交互式环境，自动继续...")
    else:
        print("✅ 自动确认模式，开始下载和上传...")
    
    # 批量处理
    success_count = 0
    for i, bird in enumerate(missing_birds, 1):
        print(f"\n[{i}/{len(missing_birds)}] 处理: {bird['slug']}")
        
        # 下载
        if download_macaulay_for_bird(bird, bird_info_dict):
            # 上传
            if upload_to_cloudinary(bird['slug']):
                success_count += 1
        else:
            print(f"⚠️  跳过上传（下载失败）")
    
    print()
    print("="*60)
    print(f"完成！成功处理 {success_count}/{len(missing_birds)} 个鸟类")
    print("="*60)

if __name__ == "__main__":
    main()

