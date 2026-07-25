#!/usr/bin/env python3
"""
同步主目录的 sounds 字段到 location_birds 目录中的 JSON 文件
用于更新已存在的 location_birds JSON，添加 sounds 字段
"""

import json
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
LOCATION_BIRDS_DIR = PROJECT_ROOT / "feather-flash-quiz" / "location_birds"
CLOUDINARY_DIR = PROJECT_ROOT / "cloudinary_uploads"


def sync_sounds_to_location_json(location_json: Path, main_json: Path):
    """
    将主目录 JSON 的 sounds 字段同步到 location_birds 的 JSON
    """
    if not main_json.exists():
        return False
    
    # 读取主目录的 JSON
    with open(main_json, 'r', encoding='utf-8') as f:
        main_data = json.load(f)
    
    main_sounds = main_data.get('sounds', [])
    
    if not main_sounds:
        # 主目录也没有 sounds，跳过
        return False
    
    # 读取 location 的 JSON
    if not location_json.exists():
        return False
    
    with open(location_json, 'r', encoding='utf-8') as f:
        loc_data = json.load(f)
    
    # 检查是否需要更新：数量相同也可能内容已被纠正（错误鸟声替换）
    loc_sounds = loc_data.get('sounds', [])

    if loc_sounds == main_sounds:
        return False

    # 更新 sounds 字段
    loc_data['sounds'] = main_sounds

    # 保存
    with open(location_json, 'w', encoding='utf-8') as f:
        json.dump(loc_data, f, indent=2, ensure_ascii=False)

    return True


def sync_all_location_birds():
    """
    遍历所有 location_birds 目录，同步 sounds 字段
    支持新结构（城市/地点/日期）和旧结构（地点/日期）
    """
    print("=" * 80)
    print("同步 sounds 字段到 location_birds 目录")
    print("=" * 80)
    print()
    
    if not LOCATION_BIRDS_DIR.exists():
        print(f"❌ location_birds 目录不存在: {LOCATION_BIRDS_DIR}")
        return
    
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    # 使用 rglob 递归查找所有 JSON 文件，自动支持新旧结构
    json_files = list(LOCATION_BIRDS_DIR.rglob("*_cloudinary_urls.json"))
    
    if not json_files:
        print("⚠️  未找到任何 JSON 文件")
        return
    
    # 按路径分组，便于显示进度
    files_by_path = {}
    for json_file in json_files:
        # 获取相对路径用于显示
        rel_path = json_file.relative_to(LOCATION_BIRDS_DIR)
        path_key = str(rel_path.parent)
        if path_key not in files_by_path:
            files_by_path[path_key] = []
        files_by_path[path_key].append(json_file)
    
    # 按路径排序处理
    for path_key in sorted(files_by_path.keys()):
        json_files_in_path = files_by_path[path_key]
        print(f"📍 {path_key}")
        
        local_updated = 0
        for json_file in json_files_in_path:
            slug = json_file.stem.replace('_cloudinary_urls', '')
            main_json = CLOUDINARY_DIR / json_file.name
            
            try:
                if sync_sounds_to_location_json(json_file, main_json):
                    local_updated += 1
                    updated_count += 1
                else:
                    skipped_count += 1
            except Exception as e:
                print(f"  ✗ {slug}: {e}")
                error_count += 1
        
        if local_updated > 0:
            print(f"  ✓ 更新了 {local_updated} 个 JSON")
    
    print()
    print("=" * 80)
    print("同步完成")
    print("=" * 80)
    print(f"✅ 已更新: {updated_count} 个 JSON 文件")
    print(f"⏭️  已跳过: {skipped_count} 个（已是最新或无 sounds）")
    if error_count > 0:
        print(f"❌ 错误: {error_count} 个")
    print("=" * 80)


if __name__ == '__main__':
    sync_all_location_birds()

