#!/usr/bin/env python3
"""
地点相关的工具函数
"""

import json
from pathlib import Path
from typing import Dict, Optional

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CONFIG_PATH = PROJECT_ROOT / "config" / "birdreport_locations.json"

# 缓存配置数据
_location_to_city_cache: Optional[Dict[str, str]] = None


def load_location_config() -> Dict[str, str]:
    """从配置文件加载地点到城市的映射"""
    global _location_to_city_cache
    
    if _location_to_city_cache is not None:
        return _location_to_city_cache
    
    if not CONFIG_PATH.exists():
        # 如果配置文件不存在，返回空字典（使用默认值）
        _location_to_city_cache = {}
        return _location_to_city_cache
    
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
    
    _location_to_city_cache = location_to_city
    return location_to_city


def get_city_for_location(location_name: str) -> str:
    """根据地点名称获取城市名称"""
    location_to_city = load_location_config()
    return location_to_city.get(location_name, '北京')  # 默认北京


def get_location_birds_path(location: str, date: str) -> Path:
    """获取 location_birds 目录下的完整路径（包含城市层级）"""
    city = get_city_for_location(location)
    return PROJECT_ROOT / "feather-flash-quiz" / "location_birds" / city / location / date














