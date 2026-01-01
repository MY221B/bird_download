#!/usr/bin/env python3
"""
根据 public_id 列表删除本地图片文件。

public_id 格式: bird-gallery/<bird_slug>/<source>/<filename>
对应本地路径: images/<bird_slug>/<source>/<filename>.jpg (或其他扩展名)
"""

import json
import sys
from pathlib import Path

def load_public_ids(p: Path):
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [item["public_id"] for item in data["items"] if item and item.get("public_id")]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, str) and x]
    raise ValueError("无法识别的JSON结构")


def delete_local_images(public_ids: list, images_dir: Path = Path("images")):
    """从 public_id 解析出本地文件路径并删除"""
    deleted_count = 0
    not_found_count = 0
    
    for public_id in public_ids:
        # public_id 格式: bird-gallery/<bird_slug>/<source>/<filename>
        if not public_id.startswith("bird-gallery/"):
            continue
        
        # 移除 "bird-gallery/" 前缀
        parts = public_id.replace("bird-gallery/", "").split("/")
        if len(parts) < 3:
            continue
        
        bird_slug = parts[0]
        source = parts[1]
        filename_base = "/".join(parts[2:])  # 处理可能有多个层级的情况
        
        # 构建可能的文件路径
        local_dir = images_dir / bird_slug / source
        
        if not local_dir.exists():
            continue
        
        # 尝试不同的扩展名
        extensions = ['.jpg', '.jpeg', '.png']
        found = False
        
        for ext in extensions:
            local_file = local_dir / f"{filename_base}{ext}"
            if local_file.exists():
                try:
                    local_file.unlink()
                    print(f"🗑️  删除本地文件: {local_file}")
                    deleted_count += 1
                    found = True
                    break
                except Exception as e:
                    print(f"⚠️  删除失败 {local_file}: {e}")
        
        if not found:
            not_found_count += 1
            # 尝试查找所有可能的文件（可能有不同的命名）
            all_files = list(local_dir.glob(f"*{filename_base}*"))
            if all_files:
                for f in all_files:
                    try:
                        f.unlink()
                        print(f"🗑️  删除本地文件（模糊匹配）: {f}")
                        deleted_count += 1
                    except Exception as e:
                        print(f"⚠️  删除失败 {f}: {e}")
    
    print(f"\n✅ 本地文件删除完成：删除 {deleted_count} 个文件，未找到 {not_found_count} 个")


def main():
    if len(sys.argv) < 2:
        print("用法: python tools/delete_local_images_by_list.py <delete_list.json>")
        sys.exit(1)
    
    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"❌ 文件不存在: {json_path}")
        sys.exit(1)
    
    public_ids = load_public_ids(json_path)
    if not public_ids:
        print("⚠️  无需删除，列表为空")
        return
    
    images_dir = Path("images")
    if not images_dir.exists():
        print(f"⚠️  images 目录不存在，跳过本地文件删除")
        return
    
    delete_local_images(public_ids, images_dir)


if __name__ == "__main__":
    main()







