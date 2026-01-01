#!/usr/bin/env python3
"""
从Avibase获取鸟类图片
"""

import urllib.request
import urllib.parse
import re
import ssl
import os
import sys
import json
from html.parser import HTMLParser

# 创建SSL context，跳过证书验证
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# 单次抓取并复用的 CN 清单 HTML 缓存
_CN_CHECKLIST_HTML_CACHE = None

def fetch_cn_checklist_html(force: bool = False) -> str:
    """获取中国名录页面HTML，支持：
    - 单次抓取并缓存（同一进程内多次查询共用）
    - 环境变量 AVIBASE_CN_HTML 指定本地HTML文件（便于批量解析与测试）
    """
    global _CN_CHECKLIST_HTML_CACHE
    if not force and _CN_CHECKLIST_HTML_CACHE is not None:
        return _CN_CHECKLIST_HTML_CACHE  # type: ignore

    local_path = os.environ.get('AVIBASE_CN_HTML', '').strip()
    if local_path:
        try:
            with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                _CN_CHECKLIST_HTML_CACHE = f.read()
            print(f"   CN清单: 本地文件 {local_path}")
            return _CN_CHECKLIST_HTML_CACHE  # type: ignore
        except Exception as e:
            print(f"   ⚠️  读取本地CN清单失败: {e}，改为在线抓取")

    url = "https://avibase.bsc-eoc.org/checklist.jsp?region=CN&list=clements_2024&lang=EN"
    print(f"   CN清单: {url}")
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36'
    })
    with urllib.request.urlopen(req, context=ssl_context) as resp:
        _CN_CHECKLIST_HTML_CACHE = resp.read().decode('utf-8', 'ignore')
    return _CN_CHECKLIST_HTML_CACHE  # type: ignore

def _parse_cn_rows(html: str):
    """解析CN清单HTML，返回[(en, sci, cn, avibaseid), ...]，
    组合 HTMLParser（主） + 正则兜底，并做去重。
    """
    class CNTableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_tr = False
            self.in_td = False
            self.td_index = -1
            self.in_i = False
            self.cur_en = []
            self.cur_sci = []
            self.cur_cn = []
            self.cur_id = ''
            self.rows = []

        def handle_starttag(self, tag, attrs):
            tag = tag.lower()
            if tag == 'tr':
                self.in_tr = True
                self.in_td = False
                self.td_index = -1
                self.in_i = False
                self.cur_en, self.cur_sci, self.cur_cn = [], [], []
                self.cur_id = ''
            elif self.in_tr and tag == 'td':
                self.in_td = True
                self.td_index += 1
            elif self.in_tr and tag == 'a':
                href = dict(attrs).get('href', '')
                m = re.search(r"species\.jsp\?avibaseid=([A-F0-9]{16})", href, re.IGNORECASE)
                if m:
                    self.cur_id = m.group(1)
            elif self.in_tr and tag == 'i':
                self.in_i = True

        def handle_endtag(self, tag):
            tag = tag.lower()
            if tag == 'td':
                self.in_td = False
                self.in_i = False
            elif tag == 'i':
                self.in_i = False
            elif tag == 'tr' and self.in_tr:
                en = ' '.join(''.join(self.cur_en).split())
                sci = ' '.join(''.join(self.cur_sci).split())
                cn = ' '.join(''.join(self.cur_cn).split())
                if self.cur_id:
                    self.rows.append((en, sci, cn, self.cur_id))
                self.in_tr = False

        def handle_data(self, data):
            if not (self.in_tr and self.in_td):
                return
            if self.td_index == 0:
                self.cur_en.append(data)
            elif self.td_index == 1 and self.in_i:
                self.cur_sci.append(data)
            elif self.td_index >= 2:
                self.cur_cn.append(data)

    parser = CNTableParser()
    parser.feed(html)
    rows = list(parser.rows)

    # 兜底：正则从<tr>片段抓取
    def fallback_parse_rows(full_html: str):
        out = []
        pat = re.compile(
            r"<tr[^>]*>\s*<td>(?P<en>.*?)</td>\s*<td>\s*<a[^>]*href=\"species\\.jsp\?avibaseid=(?P<id>[A-F0-9]{16})\"[^>]*>\s*<i>(?P<sci>[^<]+)</i>\s*</a>\s*</td>\s*<td>(?P<cn>.*?)</td>\s*</tr>",
            re.IGNORECASE | re.DOTALL,
        )
        def strip_tags(s: str) -> str:
            s = re.sub(r"<[^>]+>", " ", s)
            s = " ".join(s.split())
            return s
        for m in pat.finditer(full_html):
            en = strip_tags(m.group('en'))
            sci = strip_tags(m.group('sci'))
            cn = strip_tags(m.group('cn'))
            aid = m.group('id')
            out.append((en, sci, cn, aid))
        return out

    fb_rows = fallback_parse_rows(html)
    seen, merged = set(), []
    for en, sci, cn, aid in rows + fb_rows:
        if aid not in seen:
            seen.add(aid)
            merged.append((en, sci, cn, aid))
    return merged

def search_cn_checklist(scientific_name: str, common_name: str):
    """仅从中国名录(checklist.jsp?region=CN)解析表格，返回匹配行的 avibaseid 列表（按出现顺序）。
    匹配：同一 <tr> 中的英文名/学名/中文名任意一个与入参匹配（不区分大小写，允许空格差异）。
    支持单次抓取缓存与本地HTML覆盖（AVIBASE_CN_HTML）。
    """
    try:
        html = fetch_cn_checklist_html(force=False)
        rows = _parse_cn_rows(html)
        sci_norm = (scientific_name or '').strip().lower()
        en_norm = (common_name or '').strip().lower()
        ids = []
        for en, sci, cn, avb in rows:
            en_l = en.lower()
            sci_l = sci.lower()
            if (sci_norm and sci_l == sci_norm) or (en_norm and (en_norm == en_l or en_norm in en_l)):
                ids.append(avb)
        ids = list(dict.fromkeys(ids))
        if ids:
            print(f"   ✅ CN清单命中 {len(ids)} 个候选: {', '.join(ids[:5])}{' ...' if len(ids)>5 else ''}")
        else:
            print("   ⚠️  CN清单未命中")
        return ids
    except Exception as e:
        print(f"   ⚠️  CN清单获取失败: {e}")
        return []

def search_cn_checklist_multi(queries):
    """批量查询（单次抓取，复用HTML）。
    参数：[(scientific_name, common_name), ...]
    返回：{ (scientific_name, common_name): [avibaseid, ...] }
    """
    html = fetch_cn_checklist_html(force=False)
    rows = _parse_cn_rows(html)
    result = {}
    for sci_in, en_in in queries:
        sci_norm = (sci_in or '').strip().lower()
        en_norm = (en_in or '').strip().lower()
        ids = []
        for en, sci, cn, avb in rows:
            en_l = en.lower()
            sci_l = sci.lower()
            if (sci_norm and sci_l == sci_norm) or (en_norm and (en_norm == en_l or en_norm in en_l)):
                ids.append(avb)
        result[(sci_in, en_in)] = list(dict.fromkeys(ids))
    print(f"   ✅ 批量查询完成，共 {len(queries)} 个物种")
    return result


def search_avibase(bird_name):
    """仅使用中国名录页面作为候选来源，返回 avibaseid 列表。
    兼容旧接口，内部走单次抓取缓存。
    """
    candidates_overall = []
    try:
        ids = search_cn_checklist(scientific_name=bird_name, common_name=bird_name)
        candidates_overall.extend(ids)
    except Exception:
        pass
    if not candidates_overall:
        print(f"   ❌ 未找到物种")
        return []
    return candidates_overall

def get_flickr_photos(avibaseid):
    """获取物种的Flickr照片URL"""
    # 修改为访问Flickr标签页，这里有更多照片
    species_url = f"https://avibase.bsc-eoc.org/species.jsp?avibaseid={avibaseid}&lang=EN&sec=flickr"
    
    print(f"\n📥 获取Flickr照片...")
    print(f"   URL: {species_url}")
    
    try:
        with urllib.request.urlopen(species_url, context=ssl_context) as response:
            html = response.read().decode('utf-8')
            
            # 查找Flickr图片URL
            # 格式: https://live.staticflickr.com/XXXX/YYYYYY_ZZZZ_SIZE.jpg
            flickr_pattern = r'(https://live\.staticflickr\.com/[^"\']+_[a-z]\.jpg)'
            flickr_matches = re.findall(flickr_pattern, html)
            
            # 也查找farm格式
            farm_pattern = r'(https://farm[0-9]+\.staticflickr\.com/[^"\']+_[a-z]\.jpg)'
            farm_matches = re.findall(farm_pattern, html)
            
            # 合并并去重
            all_photos = list(dict.fromkeys(flickr_matches + farm_matches))  # 保持顺序的去重
            
            if all_photos:
                print(f"   ✅ 找到 {len(all_photos)} 张照片")
                
                # 转换为大图URL
                large_photos = []
                for url in all_photos[:10]:  # 只显示前10个
                    # 将_n.jpg (small 320) 替换为 _b.jpg (large 1024)
                    large_url = re.sub(r'_[a-z]\.jpg$', '_b.jpg', url)
                    large_photos.append(large_url)
                
                # 显示前3张的URL
                print(f"   将下载前3张:")
                for i, url in enumerate(large_photos[:3], 1):
                    print(f"      {i}. {url}")
                
                return large_photos
            else:
                print(f"   ⚠️  未找到照片")
                return []
    
    except Exception as e:
        print(f"   ❌ 错误: {e}")
        return []

def download_image(url, output_path):
    """下载图片"""
    try:
        print(f"\n   📥 下载: {os.path.basename(output_path)}")
        
        with urllib.request.urlopen(url, context=ssl_context) as response:
            data = response.read()
            
            with open(output_path, 'wb') as f:
                f.write(data)
            
            size_kb = len(data) / 1024
            print(f"      ✅ 成功: {size_kb:.1f}KB")
            return True
            
    except Exception as e:
        print(f"      ❌ 失败: {e}")
        return False

def download_avibase_photos(bird_name, scientific_name, output_dir, avibaseid_override=None, target_count: int = 3):
    """下载Avibase上的鸟类照片
    - 若单张下载失败，将自动跳过并尝试下一张，直到凑满 target_count 或无更多可用链接。
    - 保存下载的照片元数据（Flickr photo ID等）
    """
    
    print("="*60)
    print(f"从Avibase下载: {bird_name}")
    print(f"学名: {scientific_name}")
    print("="*60)
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 初始化元数据列表
    metadata_list = []
    
    # 1. 获取 avibaseid（优先使用传入的覆盖）；否则按“第一条优先，若无图则试下一条”的顺序
    avibaseid = avibaseid_override
    if not avibaseid:
        candidates = search_avibase(scientific_name)
        if not candidates:
            print(f"\n⚠️  未找到物种信息，尝试使用英文名搜索...")
            candidates = search_avibase(bird_name)
        preselected_photos = []
        for cid in candidates[:10]:  # 按出现顺序
            photos = get_flickr_photos(cid)
            if photos:
                avibaseid = cid
                preselected_photos = photos
                break
    
    if not avibaseid:
        print(f"\n❌ 无法找到物种")
        return 0
    
    # 2. 获取照片URL（若上一步已有预选列表则复用）
    try:
        photo_urls  # type: ignore
    except NameError:
        photo_urls = []
    if not photo_urls:
        try:
            preselected_photos  # type: ignore
        except NameError:
            preselected_photos = []
    photo_urls = preselected_photos or get_flickr_photos(avibaseid)
    
    if not photo_urls:
        print(f"\n⚠️  没有可用的照片")
        return 0
    
    # 3. 下载照片（获取前3张）
    print(f"\n📥 开始下载照片到: {output_dir}")
    print(f"   共找到 {len(photo_urls)} 张，将尝试下载 {target_count} 张")

    success_count = 0
    tried = 0
    seq = 1
    for url in photo_urls:
        if success_count >= target_count:
            break
        tried += 1
        filename = url.split('/')[-1]
        output_filename = f"avibase_{seq}_{filename}"
        output_path = os.path.join(output_dir, output_filename)
        
        # 提取 Flickr photo ID（从文件名）
        # 格式: PHOTOID_SECRET_SIZE.jpg
        flickr_id_match = re.match(r'(\d+)_[a-z0-9]+_[a-z]\.jpg', filename)
        flickr_id = flickr_id_match.group(1) if flickr_id_match else None
        
        if download_image(url, output_path):
            success_count += 1
            
            # 保存元数据
            photo_metadata = {
                'filename': output_filename,
                'flickr_photo_id': flickr_id,
                'flickr_url': f"https://www.flickr.com/photo.gne?id={flickr_id}" if flickr_id else None,
                'source_url': url,
                'note': '署名信息需从Flickr获取'
            }
            metadata_list.append(photo_metadata)
            
            seq += 1

    # 保存元数据到JSON文件
    if metadata_list:
        # 查找父目录的 download_metadata.json
        parent_dir = os.path.dirname(output_dir)
        metadata_file = os.path.join(parent_dir, 'download_metadata.json')
        
        # 读取现有元数据或创建新的
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r', encoding='utf-8') as f:
                all_metadata = json.load(f)
        else:
            all_metadata = {'macaulay': [], 'inaturalist': [], 'wikimedia': [], 'avibase': []}
        
        # 更新 avibase 部分
        all_metadata['avibase'] = metadata_list
        
        # 保存
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(all_metadata, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 元数据已保存到: {metadata_file}")

    print(f"\n[日志] Avibase 下载统计: 尝试 {tried}，成功 {success_count}，目标 {target_count}")
    print(f"\n{'='*60}")
    print(f"✅ 下载完成: {success_count}/{target_count} 张照片")
    print(f"{'='*60}\n")
    
    return success_count

def parse_batch_file(batch_path: str):
    """解析批量文件。支持CSV或TXT：
    - 逗号/制表符分隔: common_name, scientific_name, output_dir
    - 或三列用空白分隔（common_name 学名 输出目录）
    - 忽略空行与以#开头的注释行
    返回: [(common, scientific, output_dir)]
    """
    rows = []
    with open(batch_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in re.split(r"[,\t]", line)]
            if len(parts) < 3:
                parts = line.split()
            if len(parts) < 3:
                print(f"   ⚠️  跳过无法解析的行: {line}")
                continue
            common, scientific, outdir = parts[0], parts[1], ' '.join(parts[2:])
            rows.append((common, scientific, outdir))
    return rows

def main():
    """主函数"""
    args = sys.argv[1:]
    if not args or ('--help' in args or '-h' in args):
        print("用法:")
        print("  单个物种: python3 download_from_avibase.py <英文名> <学名> <输出目录> [avibaseid] [target_count]")
        print("  批量模式: python3 download_from_avibase.py --batch <文件路径> [target_count]")
        print("示例:")
        print("  python3 download_from_avibase.py \"Oriental Greenfinch\" \"Chloris sinica\" \"images/goldfinch/avibase\"")
        print("  python3 download_from_avibase.py --batch birds.csv 3")
        sys.exit(0)

    target_count = 3
    try:
        if args[0] == '--batch':
            if len(args) < 2:
                print("❌ 缺少批量文件路径")
                sys.exit(1)
            batch_file = args[1]
            if len(args) >= 3 and args[2].isdigit():
                target_count = int(args[2])
            rows = parse_batch_file(batch_file)
            if not rows:
                print("⚠️  批量文件为空或不可解析")
                sys.exit(1)
            # 单次抓取并缓存CN清单（若未设置ENV则联网抓取一次）
            try:
                fetch_cn_checklist_html(force=False)
            except Exception as e:
                print(f"⚠️  预抓取CN清单失败: {e}")
            total_success = 0
            for common, scientific, outdir in rows:
                cnt = download_avibase_photos(common, scientific, outdir, avibaseid_override=None, target_count=target_count)
                total_success += cnt
            print(f"\n✅ 批量完成，合计成功下载 {total_success} 张")
            return
        else:
            # 单物种模式
            if len(args) < 3:
                print("❌ 参数不足。用法: python3 download_from_avibase.py <英文名> <学名> <输出目录> [avibaseid] [target_count]")
                sys.exit(1)
            bird_name = args[0]
            scientific_name = args[1]
            output_dir = args[2]
            avibaseid_override = args[3] if len(args) >= 4 and len(args[3]) == 16 else None
            if len(args) >= 4 and args[3].isdigit():
                target_count = int(args[3])
            if len(args) >= 5 and args[4].isdigit():
                target_count = int(args[4])
            count = download_avibase_photos(bird_name, scientific_name, output_dir, avibaseid_override, target_count=target_count)
            if count > 0:
                print(f"✅ 成功下载 {count} 张Avibase照片")
            else:
                print(f"⚠️  未能下载照片")
    except KeyboardInterrupt:
        print("\n⏹️  已中断")

if __name__ == "__main__":
    main()

