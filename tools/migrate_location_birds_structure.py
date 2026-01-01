#!/usr/bin/env python3
"""
迁移 location_birds 文件夹结构
从 location_birds/{地点}/{日期}/ 迁移到 location_birds/{城市}/{地点}/{日期}/

使用方法:
    python3 tools/migrate_location_birds_structure.py [--dry-run]
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Dict, Optional

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
LOCATION_BIRDS_DIR = PROJECT_ROOT / "feather-flash-quiz" / "location_birds"
CONFIG_PATH = PROJECT_ROOT / "config" / "birdreport_locations.json"


def load_location_config() -> Dict[str, str]:
    """从配置文件加载地点到城市的映射"""
    if not CONFIG_PATH.exists():
        print(f"⚠️  配置文件不存在: {CONFIG_PATH}")
        return {}
    
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    locations = data.get('locations', [])
    location_to_city = {}
    
    for loc in locations:
        name = loc.get('name', '')
        city = loc.get('city', '')
        province = loc.get('province', '')
        
        # 提取城市名称
        if city and city.strip():
            city_name = city
        elif province:
            # 从省份提取：北京市 -> 北京
            if province.endswith('市'):
                city_name = province[:-1]
            elif province.endswith('省'):
                # 特殊处理：陕西省 -> 西安（根据实际情况调整）
                if '陕西' in province:
                    city_name = '西安'
                else:
                    city_name = province[:-1]
            else:
                city_name = province
        else:
            city_name = '北京'  # 默认值
        
        location_to_city[name] = city_name
        
        # 也添加别名映射
        aliases = loc.get('point_aliases', [])
        for alias in aliases:
            location_to_city[alias] = city_name
    
    return location_to_city


def get_city_for_location(location_name: str, location_to_city: Dict[str, str]) -> str:
    """根据地点名称获取城市"""
    return location_to_city.get(location_name, '北京')  # 默认北京


def migrate_location_birds(dry_run: bool = False):
    """迁移 location_birds 文件夹结构"""
    if not LOCATION_BIRDS_DIR.exists():
        print(f"❌ location_birds 目录不存在: {LOCATION_BIRDS_DIR}")
        return
    
    print("📋 加载地点配置...")
    location_to_city = load_location_config()
    print(f"✅ 加载了 {len(location_to_city)} 个地点映射\n")
    
    # 统计信息
    migrated_count = 0
    skipped_count = 0
    error_count = 0
    
    # 遍历所有地点目录
    for location_dir in LOCATION_BIRDS_DIR.iterdir():
        if not location_dir.is_dir():
            continue
        
        location_name = location_dir.name
        
        # 跳过已经是城市名称的目录（新结构）
        if location_name in ['北京', '上海', '西安', '其他']:
            print(f"⏭️  跳过城市目录: {location_name}")
            skipped_count += 1
            continue
        
        # 获取城市名称
        city_name = get_city_for_location(location_name, location_to_city)
        
        # 目标路径：location_birds/{城市}/{地点}/
        target_city_dir = LOCATION_BIRDS_DIR / city_name
        target_location_dir = target_city_dir / location_name
        
        print(f"\n📍 处理地点: {location_name} -> {city_name}/{location_name}")
        
        if target_location_dir.exists():
            print(f"  ⚠️  目标目录已存在，跳过: {target_location_dir}")
            skipped_count += 1
            continue
        
        # 迁移目录
        try:
            if not dry_run:
                # 创建目标城市目录
                target_city_dir.mkdir(parents=True, exist_ok=True)
                
                # 移动地点目录
                shutil.move(str(location_dir), str(target_location_dir))
                print(f"  ✅ 已迁移到: {target_location_dir}")
                migrated_count += 1
            else:
                print(f"  [DRY RUN] 将迁移到: {target_location_dir}")
                migrated_count += 1
        except Exception as e:
            print(f"  ❌ 迁移失败: {e}")
            error_count += 1
    
    print(f"\n📊 迁移统计:")
    print(f"  ✅ 成功: {migrated_count}")
    print(f"  ⏭️  跳过: {skipped_count}")
    print(f"  ❌ 错误: {error_count}")
    
    if dry_run:
        print("\n⚠️  这是试运行模式，未实际执行迁移")
        print("   运行时不加 --dry-run 参数来执行实际迁移")


def main():
    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv
    
    if dry_run:
        print("🔍 试运行模式（不会实际移动文件）\n")
    
    print("🚀 开始迁移 location_birds 文件夹结构...")
    print(f"   源目录: {LOCATION_BIRDS_DIR}")
    print(f"   新结构: location_birds/{{城市}}/{{地点}}/{{日期}}/\n")
    
    migrate_location_birds(dry_run=dry_run)
    
    if not dry_run:
        print("\n✅ 迁移完成！")


if __name__ == '__main__':
    main()

