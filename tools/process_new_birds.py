#!/usr/bin/env python3
"""
完整的鸟类处理工作流程脚本
从新增鸟单.txt到生成HTML展示页面的全流程

使用方法:
    python3 tools/process_new_birds.py
"""

import sys
import os
import csv
import subprocess
import json
import re
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)

# 导入工具函数
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
try:
    from load_bird_info_from_all_birds_csv import load_all_birds_csv
except ImportError:
    # 如果导入失败，定义备用函数
    def load_all_birds_csv():
        return {}


def parse_birds_to_csv(input_file, output_csv):
    """解析新增鸟单并转换成CSV"""
    print("📋 步骤1: 解析新增鸟单.txt并转换成CSV...")
    
    if not input_file.exists():
        print(f"❌ 错误: 找不到 {input_file}")
        return False
    
    # 使用parse_birdreport_table.py和convert_to_csv.py
    parse_cmd = [sys.executable, "tools/parse_birdreport_table.py", str(input_file)]
    convert_cmd = [sys.executable, "tools/convert_to_csv.py", "--auto", "-"]
    
    try:
        parse_proc = subprocess.Popen(parse_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        convert_proc = subprocess.Popen(convert_cmd, stdin=parse_proc.stdout, 
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        parse_proc.stdout.close()
        output, error = convert_proc.communicate()
        
        if convert_proc.returncode != 0:
            print(f"❌ CSV转换失败: {error.decode()}")
            return False
        
        output_csv.write_text(output.decode('utf-8'), encoding='utf-8')
        
        # 统计鸟类数量
        bird_count = len([l for l in output.decode('utf-8').split('\n') 
                         if l.strip() and not l.startswith('#')])
        print(f"✅ 成功解析 {bird_count} 种鸟类")
        return True
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False


def merge_with_all_birds_csv(csv_file):
    """合并新增鸟类CSV与all_birds.csv，优先使用all_birds.csv的信息"""
    print("\n📋 步骤1.5: 合并 all_birds.csv 信息...")
    
    # 加载all_birds.csv
    all_birds_map = load_all_birds_csv()
    print(f"📋 从 all_birds.csv 加载了 {len(all_birds_map)} 条记录")
    
    if not csv_file.exists():
        return csv_file
    
    # 读取临时CSV
    temp_birds = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
        
        # 检查字段
        header_line = None
        for i, line in enumerate(lines):
            if line.strip().startswith('#'):
                header_line = i
                break
        
        has_chinese = False
        if header_line is not None:
            header = lines[header_line].strip()
            has_chinese = 'chinese_name' in header.lower()
        
        if data_lines:
            if has_chinese:
                reader = csv.DictReader(data_lines, fieldnames=['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'])
            else:
                reader = csv.DictReader(data_lines, fieldnames=['slug', 'english_name', 'scientific_name', 'wikipedia_page'])
            
            for row in reader:
                slug = row.get('slug', '').strip()
                if slug and slug != 'slug':
                    temp_birds.append({
                        'slug': slug,
                        'chinese_name': row.get('chinese_name', '').strip('"') if has_chinese else '',
                        'english_name': row.get('english_name', '').strip('"'),
                        'scientific_name': row.get('scientific_name', '').strip('"'),
                        'wikipedia_page': row.get('wikipedia_page', '').strip()
                    })
    
    # 合并：优先使用all_birds.csv的信息
    merged_birds = []
    new_birds_count = 0
    existing_birds_count = 0
    
    for bird in temp_birds:
        slug = bird['slug']
        if slug in all_birds_map:
            # 使用all_birds.csv中的信息（更完整和准确）
            merged_bird = all_birds_map[slug].copy()
            merged_bird['slug'] = slug
            # 如果临时CSV有中文名但all_birds.csv没有，使用临时的
            if bird.get('chinese_name') and not merged_bird.get('chinese_name'):
                merged_bird['chinese_name'] = bird['chinese_name']
            merged_birds.append(merged_bird)
            existing_birds_count += 1
            # 不显示已存在的鸟类，只显示新鸟类
        else:
            # 新鸟类，使用临时CSV的信息
            merged_birds.append(bird)
            new_birds_count += 1
            english = bird.get('english_name', slug)
            chinese = bird.get('chinese_name', '')
            name_display = f"{english}（{chinese}）" if chinese else english
            print(f"  🆕 {slug} - {name_display} - 新鸟类（将添加到 all_birds.csv）")
    
    # 写回合并后的CSV
    with open(csv_file, 'w', encoding='utf-8') as f:
        f.write('# slug,chinese_name,english_name,scientific_name,wikipedia_page\n')
        for bird in merged_birds:
            chinese = bird.get('chinese_name', '')
            english = bird.get('english_name', '')
            scientific = bird.get('scientific_name', '')
            wiki = bird.get('wikipedia_page', '')
            if not wiki and english:
                wiki = english.replace(' ', '_')
            f.write(f'{bird["slug"]},"{chinese}","{english}","{scientific}",{wiki}\n')
    
    print(f"\n✅ 合并完成: {existing_birds_count} 个使用 all_birds.csv，{new_birds_count} 个新鸟类")
    return csv_file


def check_missing_birds(csv_file):
    """
    检查需要下载的新鸟类
    
    重要说明：
    - 检查逻辑：检查 cloudinary_uploads/ 目录中是否存在对应的 JSON 文件且有有效的照片 URL 数据
    - 即使 all_birds.csv 中有记录，如果 Cloudinary 上传记录不存在或没有照片，仍会下载
    - all_birds.csv 只用于提供更准确的名称信息，不影响下载判断
    """
    print("\n📋 步骤2: 检查需要下载的新鸟类...")
    missing = []
    
    # 加载all_birds.csv（仅用于显示信息，不影响下载判断）
    all_birds_map = load_all_birds_csv()
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
        
        # 检查字段
        header_line = None
        for i, line in enumerate(lines):
            if line.strip().startswith('#'):
                header_line = i
                break
        
        has_chinese = False
        if header_line is not None:
            header = lines[header_line].strip()
            has_chinese = 'chinese_name' in header.lower()
        
        if data_lines:
            if has_chinese:
                reader = csv.DictReader(data_lines, fieldnames=['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'])
            else:
                reader = csv.DictReader(data_lines, fieldnames=['slug', 'english_name', 'scientific_name', 'wikipedia_page'])
            
            for row in reader:
                slug = row.get('slug', '').strip()
                if slug and slug != 'slug':
                    # 关键：检查 cloudinary_uploads/ 目录中是否存在 JSON 文件且有有效的照片 URL 数据
                    json_file = PROJECT_ROOT / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
                    in_all_birds = slug in all_birds_map  # 仅用于显示信息
                    
                    has_cloudinary_data = False
                    photo_count = 0
                    
                    if json_file.exists():
                        try:
                            with open(json_file, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                # 检查是否有有效的照片 URL 数据（至少有一个源有照片）
                                for source in ['macaulay', 'inaturalist', 'wikimedia', 'avibase']:
                                    if source in data and isinstance(data[source], list):
                                        photo_count += len(data[source])
                                has_cloudinary_data = photo_count > 0
                        except Exception:
                            has_cloudinary_data = False
                    
                    # 获取鸟类名称用于显示
                    bird_info = all_birds_map.get(slug) or {}
                    english = bird_info.get('english_name') or row.get('english_name', '').strip('"') or slug
                    chinese = bird_info.get('chinese_name') or row.get('chinese_name', '').strip('"')
                    name_display = f"{english}（{chinese}）" if chinese else english
                    
                    if has_cloudinary_data:
                        # Cloudinary 已有上传记录且有照片，不需要下载
                        status = f"已上传到 Cloudinary（{photo_count} 张照片）"
                        if in_all_birds:
                            status += "，也在 all_birds.csv 中"
                        print(f"  ✅ {slug} - {name_display} - {status}")
                    else:
                        # Cloudinary 没有上传记录或没有照片，需要下载
                        if in_all_birds:
                            if json_file.exists():
                                print(f"  📥 {slug} - {name_display} - 需要下载（已在 all_birds.csv 中，但 Cloudinary 记录缺失照片）")
                            else:
                                print(f"  📥 {slug} - {name_display} - 需要下载（已在 all_birds.csv 中，但未上传到 Cloudinary）")
                        else:
                            print(f"  🆕 {slug} - {name_display} - 需要下载（新鸟类）")
                        missing.append(slug)
    
    return missing


def download_birds(csv_file, missing_birds):
    """批量下载新鸟类图片"""
    if not missing_birds:
        print("✅ 所有鸟类图片已存在，跳过下载步骤")
        return True
    
    print(f"\n📥 步骤3: 批量下载新鸟类的图片...")
    print(f"需要下载 {len(missing_birds)} 种鸟类")
    
    # 获取鸟类名称信息用于显示
    all_birds_map = load_all_birds_csv()
    bird_names = []
    for slug in missing_birds:
        bird_info = all_birds_map.get(slug, {})
        english = bird_info.get('english_name', slug)
        chinese = bird_info.get('chinese_name', '')
        if chinese:
            bird_names.append(f"{english}（{chinese}）")
        else:
            bird_names.append(english)
    
    if bird_names:
        print("需要下载的鸟类:")
        for name in bird_names:
            print(f"  - {name}")
    
    # 检查EBIRD_TOKEN，如果不存在则尝试从 config/ebird_token.sh 读取
    ebird_token = os.environ.get('EBIRD_TOKEN')
    if not ebird_token:
        # 尝试从 config/ebird_token.sh 读取
        token_file = PROJECT_ROOT / "config" / "ebird_token.sh"
        if token_file.exists():
            try:
                with open(token_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 使用正则表达式提取 export EBIRD_TOKEN=xxx
                    import re
                    match = re.search(r'export\s+EBIRD_TOKEN\s*=\s*([^\s\n]+)', content)
                    if match:
                        ebird_token = match.group(1).strip().strip('"').strip("'")
                        os.environ['EBIRD_TOKEN'] = ebird_token
                        print(f"✅ 从 {token_file} 自动加载了 EBIRD_TOKEN")
                    else:
                        print(f"⚠️  警告: 在 {token_file} 中未找到 EBIRD_TOKEN")
                        print("请运行: export EBIRD_TOKEN=your_token")
                        return False
            except Exception as e:
                print(f"⚠️  警告: 读取 {token_file} 失败: {e}")
                print("请运行: export EBIRD_TOKEN=your_token")
                return False
        else:
            print("⚠️  警告: 未设置 EBIRD_TOKEN 环境变量")
            print("请运行: export EBIRD_TOKEN=your_token")
            print(f"或确保 {token_file} 文件存在")
            return False
    
    # 创建只包含缺失鸟类的临时CSV文件
    missing_birds_set = set(missing_birds)
    temp_csv = PROJECT_ROOT / "new_birds_missing_only.csv"
    
    try:
        # 尝试多种编码读取CSV文件
        lines = None
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'cp1252']
        for encoding in encodings:
            try:
                with open(csv_file, 'r', encoding=encoding) as f_in:
                    lines = f_in.readlines()
                    if encoding != 'utf-8':
                        print(f"ℹ️  使用 {encoding} 编码读取 CSV 文件")
                    break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if lines is None:
            raise Exception(f"无法读取 CSV 文件，尝试了以下编码: {', '.join(encodings)}")
        
        header_line = None
        for i, line in enumerate(lines):
            if line.strip().startswith('#'):
                header_line = i
                break
        
        with open(temp_csv, 'w', encoding='utf-8') as f_out:
                # 写入表头
                if header_line is not None:
                    f_out.write(lines[header_line])
                
                # 只写入缺失的鸟类
                data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
                has_chinese = False
                if header_line is not None:
                    header = lines[header_line].strip()
                    has_chinese = 'chinese_name' in header.lower()
                
                if data_lines:
                    if has_chinese:
                        reader = csv.DictReader(data_lines, fieldnames=['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'])
                    else:
                        reader = csv.DictReader(data_lines, fieldnames=['slug', 'english_name', 'scientific_name', 'wikipedia_page'])
                    
                    for row in reader:
                        slug = row.get('slug', '').strip()
                        if slug and slug in missing_birds_set:
                            # 写入这一行
                            if has_chinese:
                                f_out.write(f"{slug},{row.get('chinese_name', '')},{row.get('english_name', '')},{row.get('scientific_name', '')},{row.get('wikipedia_page', '')}\n")
                            else:
                                f_out.write(f"{slug},{row.get('english_name', '')},{row.get('scientific_name', '')},{row.get('wikipedia_page', '')}\n")
        
        # 批量下载（使用临时CSV文件，并添加--skip-existing参数以避免重复下载）
        batch_script = PROJECT_ROOT / "tools" / "batch_fetch.sh"
        if not batch_script.exists():
            print(f"❌ 找不到批量下载脚本: {batch_script}")
            return False
        
        try:
            result = subprocess.run([str(batch_script), str(temp_csv), "--parallel", "3", "--skip-existing"], 
                                   check=True, capture_output=True, text=True)
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ 下载失败: {e.stderr}")
            # 即使下载脚本失败，也检查一下是否有部分图片已经下载成功
            print("ℹ️  检查是否有部分图片已下载...")
            downloaded_count = 0
            for slug in missing_birds:
                bird_path = PROJECT_ROOT / "images" / slug
                if bird_path.exists():
                    has_images = False
                    for source_dir in ['macaulay', 'inaturalist', 'wikimedia', 'avibase']:
                        source_path = bird_path / source_dir
                        if source_path.exists():
                            image_files = list(source_path.glob("*.jpg")) + list(source_path.glob("*.jpeg")) + list(source_path.glob("*.png"))
                            if image_files:
                                has_images = True
                                break
                    if has_images:
                        downloaded_count += 1
            if downloaded_count > 0:
                print(f"ℹ️  发现 {downloaded_count}/{len(missing_birds)} 种鸟类已有本地图片")
            return False
        finally:
            # 清理临时文件
            if temp_csv.exists():
                temp_csv.unlink()
                
    except Exception as e:
        print(f"❌ 创建临时CSV文件失败: {e}")
        # 即使创建临时CSV失败，也检查一下是否有部分图片已经下载成功
        print("ℹ️  检查是否有部分图片已下载...")
        downloaded_count = 0
        for slug in missing_birds:
            bird_path = PROJECT_ROOT / "images" / slug
            if bird_path.exists():
                has_images = False
                for source_dir in ['macaulay', 'inaturalist', 'wikimedia', 'avibase']:
                    source_path = bird_path / source_dir
                    if source_path.exists():
                        image_files = list(source_path.glob("*.jpg")) + list(source_path.glob("*.jpeg")) + list(source_path.glob("*.png"))
                        if image_files:
                            has_images = True
                            break
                if has_images:
                    downloaded_count += 1
        if downloaded_count > 0:
            print(f"ℹ️  发现 {downloaded_count}/{len(missing_birds)} 种鸟类已有本地图片，可以继续上传步骤")
        return False


def check_missing_cloudinary(csv_file):
    """检查需要上传到Cloudinary的鸟类（检查JSON文件是否存在且有有效的照片数据）"""
    print("\n📋 步骤4: 检查需要上传到Cloudinary的鸟类...")
    missing = []
    
    # 加载all_birds.csv用于获取中文名
    all_birds_map = load_all_birds_csv()
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
        
        # 检查字段
        header_line = None
        for i, line in enumerate(lines):
            if line.strip().startswith('#'):
                header_line = i
                break
        
        has_chinese = False
        if header_line is not None:
            header = lines[header_line].strip()
            has_chinese = 'chinese_name' in header.lower()
        
        if data_lines:
            if has_chinese:
                reader = csv.DictReader(data_lines, fieldnames=['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'])
            else:
                reader = csv.DictReader(data_lines, fieldnames=['slug', 'english_name', 'scientific_name', 'wikipedia_page'])
            
            for row in reader:
                slug = row.get('slug', '').strip()
                if slug and slug != 'slug':
                    json_file = PROJECT_ROOT / "cloudinary_uploads" / f"{slug}_cloudinary_urls.json"
                    has_cloudinary_data = False
                    photo_count = 0
                    
                    if json_file.exists():
                        try:
                            with open(json_file, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                # 检查是否有有效的照片 URL 数据（至少有一个源有照片）
                                for source in ['macaulay', 'inaturalist', 'wikimedia', 'avibase']:
                                    if source in data and isinstance(data[source], list):
                                        photo_count += len(data[source])
                                has_cloudinary_data = photo_count > 0
                        except Exception:
                            has_cloudinary_data = False
                    
                    # 获取鸟类名称用于显示
                    bird_info = all_birds_map.get(slug) or {}
                    english = bird_info.get('english_name') or row.get('english_name', '').strip('"') or slug
                    chinese = bird_info.get('chinese_name') or row.get('chinese_name', '').strip('"')
                    name_display = f"{english}（{chinese}）" if chinese else english
                    
                    if has_cloudinary_data:
                        # 不显示已上传的鸟类，只显示需要上传的
                        pass
                    else:
                        print(f"  ❌ {slug} - {name_display} - 需要上传（JSON文件{'存在但无照片' if json_file.exists() else '不存在'}）")
                        missing.append(slug)
    
    return missing


def upload_to_cloudinary(missing_birds, csv_file):
    """上传图片到Cloudinary，优先使用all_birds.csv的信息构建bird_info"""
    if not missing_birds:
        print("✅ 所有鸟类已上传到Cloudinary")
        return True
    
    print(f"\n☁️  步骤5: 上传图片到Cloudinary...")
    print(f"需要上传 {len(missing_birds)} 种鸟类")
    
    upload_script = PROJECT_ROOT / "tools" / "upload_to_cloudinary.py"
    if not upload_script.exists():
        print(f"❌ 找不到上传脚本: {upload_script}")
        return False
    
    # 优先从all_birds.csv读取信息
    all_birds_map = load_all_birds_csv()
    print(f"📋 从 all_birds.csv 加载了 {len(all_birds_map)} 条记录")
    
    # 从临时CSV读取信息（作为后备）
    bird_info_map = {}
    if csv_file.exists():
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
                
                # 检查是否有chinese_name字段
                header_line = None
                for i, line in enumerate(lines):
                    if line.strip().startswith('#'):
                        header_line = i
                        break
                
                has_chinese = False
                if header_line is not None:
                    header = lines[header_line].strip()
                    has_chinese = 'chinese_name' in header.lower()
                
                if data_lines:
                    if has_chinese:
                        reader = csv.DictReader(data_lines, fieldnames=['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'])
                    else:
                        reader = csv.DictReader(data_lines, fieldnames=['slug', 'english_name', 'scientific_name', 'wikipedia_page'])
                    
                    for row in reader:
                        slug = row['slug'].strip('"')
                        bird_info_map[slug] = {
                            'chinese_name': row.get('chinese_name', '').strip('"') if has_chinese else '',
                            'english_name': row.get('english_name', '').strip('"'),
                            'scientific_name': row.get('scientific_name', '').strip('"')
                        }
        except Exception as e:
            print(f"⚠️  读取临时CSV信息失败: {e}")
    
    # 合并：优先使用all_birds.csv
    for slug in missing_birds:
        if slug in all_birds_map:
            bird_info_map[slug] = all_birds_map[slug].copy()
    
    # 从新增鸟单.txt提取中文名
    input_file = PROJECT_ROOT / "新增鸟单.txt"
    chinese_map = {}
    if input_file.exists():
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f.readlines()]
            
            i = 0
            in_table = False
            for i, line in enumerate(lines):
                if line == '科':
                    in_table = True
                    i += 1
                    break
            
            while i < len(lines):
                line = lines[i]
                if line.isdigit() or not line:
                    i += 1
                    continue
                if re.match(r'^[\u4e00-\u9fff䴙䴘]+$', line) and i + 2 < len(lines):
                    chinese = line
                    english = lines[i+1].strip()
                    scientific = lines[i+2].strip()
                    if (re.match(r'^[A-Z]', english) and 
                        re.match(r'^[A-Z][a-z]+ [a-z]+', scientific)):
                        # 通过英文名匹配slug
                        for slug, info in bird_info_map.items():
                            if info['english_name'] == english:
                                chinese_map[slug] = chinese
                        i += 3
                        continue
                i += 1
        except Exception:
            pass
    
    for bird in missing_birds:
        # 获取鸟类名称信息用于显示
        bird_info = bird_info_map.get(bird, {})
        english = bird_info.get('english_name', bird)
        chinese = bird_info.get('chinese_name', '')
        if chinese:
            print(f"  上传: {bird} - {english}（{chinese}）")
        else:
            print(f"  上传: {bird} - {english}")
        try:
            # 构建命令参数
            cmd = [sys.executable, str(upload_script), bird]
            
            # 如果CSV中有信息，传递给上传脚本
            if bird in bird_info_map:
                info = bird_info_map[bird]
                # 使用从新增鸟单.txt提取的中文名（如果存在）
                chinese = chinese_map.get(bird, info.get('chinese_name', ''))
                if chinese and info.get('english_name') and info.get('scientific_name'):
                    cmd.extend([chinese, info['english_name'], info['scientific_name']])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"    ⚠️  {bird} 上传失败: {result.stderr}")
            else:
                print(f"    ✅ {bird} 上传成功")
        except Exception as e:
            print(f"    ❌ {bird} 上传错误: {e}")
    
    return True


def update_bird_info(csv_file):
    """更新bird_info字段（确保中文名正确）"""
    print("\n📋 步骤6: 更新bird_info字段...")
    
    # 从CSV读取鸟类信息
    bird_map = {}
    with open(csv_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
        
        # 检查是否有chinese_name字段
        header_line = None
        for i, line in enumerate(lines):
            if line.strip().startswith('#'):
                header_line = i
                break
        
        has_chinese = False
        if header_line is not None:
            header = lines[header_line].strip()
            has_chinese = 'chinese_name' in header.lower()
        
        if data_lines:
            if has_chinese:
                reader = csv.DictReader(data_lines, fieldnames=['slug', 'chinese_name', 'english_name', 'scientific_name', 'wikipedia_page'])
            else:
                reader = csv.DictReader(data_lines, fieldnames=['slug', 'english_name', 'scientific_name', 'wikipedia_page'])
            
            for row in reader:
                slug = row['slug'].strip('"')
                bird_map[slug] = {
                    'chinese_name': row.get('chinese_name', '').strip('"') if has_chinese else '',
                    'english_name': row.get('english_name', '').strip('"'),
                    'scientific_name': row.get('scientific_name', '').strip('"')
                }
    
    # 从新增鸟单.txt提取中文名
    input_file = PROJECT_ROOT / "新增鸟单.txt"
    chinese_map = {}
    
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f.readlines()]
    
    i = 0
    in_table = False
    for i, line in enumerate(lines):
        if line == '科':
            in_table = True
            i += 1
            break
    
    while i < len(lines):
        line = lines[i]
        if line.isdigit() or not line:
            i += 1
            continue
        if re.match(r'^[\u4e00-\u9fff䴙䴘]+$', line) and i + 2 < len(lines):
            chinese = line
            english = lines[i+1].strip()
            scientific = lines[i+2].strip()
            if (re.match(r'^[A-Z]', english) and 
                re.match(r'^[A-Z][a-z]+ [a-z]+', scientific)):
                # 通过英文名匹配slug
                for slug, info in bird_map.items():
                    if info['english_name'] == english:
                        chinese_map[slug] = chinese
                i += 3
                continue
        i += 1
    
    # 更新JSON文件
    upload_dir = PROJECT_ROOT / "cloudinary_uploads"
    updated = 0
    for slug, chinese in chinese_map.items():
        json_file = upload_dir / f"{slug}_cloudinary_urls.json"
        if json_file.exists():
            data = json.loads(json_file.read_text(encoding='utf-8'))
            if 'bird_info' not in data:
                data['bird_info'] = {}
            data['bird_info']['slug'] = slug
            data['bird_info']['chinese_name'] = chinese
            data['bird_info']['english_name'] = bird_map[slug]['english_name']
            data['bird_info']['scientific_name'] = bird_map[slug]['scientific_name']
            json_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            updated += 1
    
    print(f"✅ 已更新 {updated} 个JSON文件的bird_info字段")
    return True


def update_all_birds_csv():
    """从JSON文件提取鸟类信息并补全all_birds.csv"""
    print("\n📋 步骤7: 补全 all_birds.csv...")
    
    csv_update_script = PROJECT_ROOT / "tools" / "add_missing_birds_to_csv.py"
    if not csv_update_script.exists():
        print(f"⚠️  找不到CSV更新脚本: {csv_update_script}")
        return True  # 不阻塞流程
    
    try:
        result = subprocess.run([sys.executable, str(csv_update_script)],
                              capture_output=True, text=True)
        print(result.stdout)
        return True
    except Exception as e:
        print(f"⚠️  更新CSV失败: {e}，但继续后续步骤")
        return True  # 不阻塞流程


def generate_html(highlight_slugs=None, priority_slugs=None):
    """生成HTML页面"""
    print("\n📋 步骤8: 生成HTML展示页面...")
    
    # 直接调用 update_gallery_from_cloudinary 模块
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    try:
        from update_gallery_from_cloudinary import main as update_gallery_main
        
        update_gallery_main(highlight_slugs=highlight_slugs, priority_slugs=priority_slugs)
        
        return True
    except Exception as e:
        print(f"❌ 生成HTML失败: {e}")
        return False


def reorder_new_birds(csv_file):
    """确保新上传的鸟类在列表顶部"""
    print("\n📋 步骤9: 调整新上传鸟类到列表顶部...")
    
    # 获取CSV中的所有鸟类
    new_birds = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.strip().split(',')
            if len(parts) >= 1:
                slug = parts[0].strip('"')
                if slug and slug != 'slug':  # 跳过表头
                    new_birds.append(slug)
    
    # 读取现有HTML的顺序
    html_file = PROJECT_ROOT / "examples" / "gallery_all_cloudinary.html"
    if not html_file.exists():
        print("⚠️  HTML文件不存在，跳过排序")
        return True
    
    html_content = html_file.read_text(encoding='utf-8')
    existing_order = re.findall(r'data-target="([^"]+)"', html_content)
    
    # 重新生成HTML
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    from update_gallery_from_cloudinary import load_all_birds, build_html
    
    all_data = load_all_birds(PROJECT_ROOT / "cloudinary_uploads")
    
    # 过滤新鸟类：只保留在 all_data 中存在的
    new_birds_existing = [b for b in new_birds if b in all_data]
    if len(new_birds_existing) < len(new_birds):
        info_map = load_all_birds_csv()
        def format_slug(slug):
            info = info_map.get(slug, {})
            chinese = info.get('chinese_name') or info.get('chinese')
            english = info.get('english_name') or info.get('english')
            label = english or slug
            if chinese:
                return f"{label}（{chinese}）"
            return label
        missing = set(new_birds) - set(new_birds_existing)
        friendly = [format_slug(slug) for slug in missing]
        print(f"  ⚠️  以下 {len(missing)} 种鸟类还未上传到 Cloudinary，跳过排序: {', '.join(friendly[:10])}")
        if len(missing) > 10:
            print(f"    ... 还有 {len(missing) - 10} 种")
    
    # 将新上传的鸟类移到最前面
    remaining = [b for b in existing_order if b not in new_birds_existing]
    final_order = new_birds_existing + remaining
    
    # 确保所有在 all_data 中的鸟类都在 final_order 中
    all_slugs = set(all_data.keys())
    missing_in_order = all_slugs - set(final_order)
    if missing_in_order:
        final_order.extend(sorted(missing_in_order))
    
    html = build_html(all_data, final_order)
    html_file.write_text(html, encoding='utf-8')
    
    print(f"✅ 已调整顺序，{len(new_birds_existing)} 种本次处理的鸟类在列表顶部（共 {len(new_birds)} 种，{len(new_birds) - len(new_birds_existing)} 种尚未上传到 Cloudinary）")
    return True


def main():
    """主函数"""
    print("🐦 开始处理新增鸟类列表...\n")
    
    # 输入输出文件
    input_file = PROJECT_ROOT / "新增鸟单.txt"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_csv = PROJECT_ROOT / f"new_birds_{timestamp}.csv"
    
    # 步骤1: 解析并转换为CSV
    if not parse_birds_to_csv(input_file, output_csv):
        return 1
    
    # 步骤1.5: 合并 all_birds.csv 信息（优先使用all_birds.csv）
    merge_with_all_birds_csv(output_csv)
    
    # 步骤2: 检查需要下载的鸟类（会检查all_birds.csv）
    missing_birds = check_missing_birds(output_csv)
    
    # 步骤3: 下载缺失的鸟类
    if missing_birds:
        if not download_birds(output_csv, missing_birds):
            print("⚠️  下载失败，但继续后续步骤")
    
    # 步骤4: 检查需要上传的鸟类
    missing_cloudinary = check_missing_cloudinary(output_csv)
    
    # 步骤5: 上传到Cloudinary
    if missing_cloudinary:
        upload_to_cloudinary(missing_cloudinary, output_csv)
    
    # 步骤6: 更新bird_info
    update_bird_info(output_csv)
    
    # 步骤7: 补全all_birds.csv
    update_all_birds_csv()
    
    # 步骤8: 生成HTML
    generate_html()
    
    # 步骤9: 调整顺序
    reorder_new_birds(output_csv)
    
    print("\n✅ 所有步骤完成！")
    print(f"\n📄 生成的CSV文件: {output_csv}")
    print("🌐 HTML页面: examples/gallery_all_cloudinary.html")
    print("\n打开页面: open examples/gallery_all_cloudinary.html")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
