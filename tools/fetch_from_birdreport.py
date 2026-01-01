#!/usr/bin/env python3
"""
从中国观鸟记录中心提取鸟类名单

用法：
  python3 tools/fetch_from_birdreport.py <url>
  python3 tools/fetch_from_birdreport.py <url> > my_birds.txt

支持的URL格式：
  https://www.birdreport.cn/home/search/taxon.html?search=...
"""

import sys
import argparse
import urllib.request
import urllib.parse
import json
import re
import os
import base64
import time
import random
import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from html.parser import HTMLParser

try:
    import requests
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5
except ImportError:  # pragma: no cover - optional dependency
    requests = None
    AES = None
    unpad = None
    RSA = None
    PKCS1_v1_5 = None

API_URL = "https://api.birdreport.cn/front/record/activity/taxon"
PUBLIC_KEY_B64 = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCvxXa98E1uWXnBzXkS2yHUfnBM6n3PCwLd"
    "fIox03T91joBvjtoDqiQ5x3tTOfpHs3LtiqMMEafls6b0YWtgB1dse1W5m+FpeusVkCOkQxB4"
    "SZDH6tuerIknnmB/Hsq5wgEkIvO5Pff9biig6AyoAkdWpSek/1/B7zYIepYY0lxKQIDAQAB"
)
AES_KEY = "C8EB5514AF5ADDB94B2207B08C66601C".encode("utf-8")
AES_IV = "55DD79C6F04E1A67".encode("utf-8")

if requests is not None:
    try:
        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
    except Exception:
        pass


@dataclass
class BirdRecord:
    chinese: str
    english: str
    scientific: str

class BirdReportParser(HTMLParser):
    """解析观鸟记录页面的 HTML"""
    
    def __init__(self):
        super().__init__()
        self.birds = []
        self.in_table = False
        self.current_row = {}
        self.current_cell = None
        self.current_data = []
        
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.in_table = True
        elif tag == 'tr' and self.in_table:
            self.current_row = {}
        elif tag == 'td' and self.in_table:
            self.current_cell = 'cell'
            self.current_data = []
            
    def handle_endtag(self, tag):
        if tag == 'table':
            self.in_table = False
        elif tag == 'tr' and self.in_table and self.current_row:
            # 处理完整的行
            if 'chinese' in self.current_row and 'scientific' in self.current_row:
                self.birds.append(self.current_row)
            self.current_row = {}
        elif tag == 'td' and self.in_table:
            cell_text = ''.join(self.current_data).strip()
            if cell_text:
                # 尝试识别中文名和学名
                if re.search(r'[\u4e00-\u9fff]', cell_text):
                    self.current_row['chinese'] = cell_text
                elif re.match(r'^[A-Z][a-z]+ [a-z]+', cell_text):
                    self.current_row['scientific'] = cell_text
            self.current_cell = None
            self.current_data = []
            
    def handle_data(self, data):
        if self.current_cell:
            self.current_data.append(data)


def ensure_crypto_available():
    if not all([requests, AES, unpad, RSA, PKCS1_v1_5]):
        print(
            "❌ 需要安装 requests 和 pycryptodome 才能使用 API 抓取功能。\n"
            "  请执行: python3 -m pip install --user requests pycryptodome",
            file=sys.stderr,
        )
        sys.exit(1)


def dict_to_json_sorted(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def pad_base64(encoded):
    return encoded + "=" * ((4 - len(encoded) % 4) % 4)


def decode_search_param(url):
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    search_values = query.get("search")
    if not search_values:
        return None
    encoded = urllib.parse.unquote(search_values[0])
    try:
        decoded = base64.b64decode(pad_base64(encoded)).decode("utf-8")
        params = json.loads(decoded)
    except Exception as exc:
        print(f"❌ 无法解析 search 参数: {exc}", file=sys.stderr)
        return None
    payload = {}
    for key, value in params.items():
        if value is None:
            payload[key] = ""
        elif isinstance(value, (int, float)):
            payload[key] = str(value)
        else:
            payload[key] = str(value)
    return payload


def prepare_api_payload(search_payload):
    payload = {
        "taxonid": "",
        "startTime": "",
        "endTime": "",
        "province": "",
        "city": "",
        "district": "",
        "pointname": "",
        "username": "",
        "serial_id": "",
        "ctime": "",
        "version": "CH4",
        "state": "",
        "mode": "0",
        "taxon_month": "",
        "outside_type": "0",
        "limit": "1500",
        "page": "1",
    }
    if search_payload:
        payload.update({k: str(v) for k, v in search_payload.items()})

    for key in ("province", "city", "district", "pointname"):
        value = payload.get(key, "")
        payload[key] = urllib.parse.quote(value, safe="") if value else ""

    for key, value in payload.items():
        if value is None:
            payload[key] = ""
        else:
            payload[key] = str(value)
    return payload


def determine_date_range(args, entry=None):
    entry = entry or {}
    if args.start and args.end:
        return args.start, args.end
    entry_start = entry.get("startTime") or entry.get("start")
    entry_end = entry.get("endTime") or entry.get("end")
    days = args.days or entry.get("default_days")
    if entry_start and entry_end:
        return entry_start, entry_end
    if days:
        days = max(1, int(days))
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days - 1)
        return start_date.isoformat(), end_date.isoformat()
    return args.start or entry_start or "", args.end or entry_end or ""


def build_base_payload_from_args(args, entry=None):
    entry = entry or {}
    payload = {
        "taxonid": args.taxonid or "",
        "province": args.province or entry.get("province", ""),
        "city": args.city or entry.get("city", ""),
        "district": args.district or entry.get("district", ""),
        "pointname": args.pointname or entry.get("pointname", entry.get("name", "")),
        "username": args.username or entry.get("username", ""),
        "serial_id": args.serial_id or entry.get("serial_id", ""),
        "ctime": args.ctime or entry.get("ctime", ""),
        "version": args.version or entry.get("version", "CH4"),
        "state": args.state or entry.get("state", ""),
        "mode": str(args.mode if args.mode is not None else entry.get("mode", "0")),
        "taxon_month": args.taxon_month or entry.get("taxon_month", ""),
        "outside_type": str(
            args.outside_type if args.outside_type is not None else entry.get("outside_type", "0")
        ),
        "limit": str(args.limit if args.limit is not None else entry.get("limit", "1500")),
        "page": str(args.page if args.page is not None else entry.get("page", "1")),
    }
    start, end = determine_date_range(args, entry)
    payload["startTime"] = start
    payload["endTime"] = end
    if not payload.get("taxon_month") and start:
        payload["taxon_month"] = start.split("-")[1]
    return payload


def expand_alias_payloads(base_payload, aliases):
    if not aliases:
        return [base_payload]
    payloads = []
    for alias in aliases:
        alias = alias.strip()
        if not alias:
            continue
        payload = base_payload.copy()
        payload["pointname"] = alias
        payloads.append(payload)
    return payloads or [base_payload]


def split_payload_by_month(payload):
    start = payload.get("startTime")
    end = payload.get("endTime")
    if not start or not end:
        return [payload]
    try:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        return [payload]
    if start_date > end_date:
        return [payload]
    segments = []
    current = start_date
    while current <= end_date:
        month_end_day = calendar.monthrange(current.year, current.month)[1]
        month_end = date(current.year, current.month, month_end_day)
        seg_end = month_end if month_end <= end_date else end_date
        seg_payload = payload.copy()
        seg_payload["startTime"] = current.isoformat()
        seg_payload["endTime"] = seg_end.isoformat()
        seg_payload["taxon_month"] = f"{current.month:02d}"
        segments.append(seg_payload)
        current = seg_end + timedelta(days=1)
    return segments or [payload]


def fetch_birds_for_payload(raw_payload):
    ensure_crypto_available()
    normalized = prepare_api_payload(raw_payload)
    segments = split_payload_by_month(normalized)
    results = []
    for segment in segments:
        results.extend(call_api_with_payload(segment))
    return results


def call_api_with_payload(payload):
    params_str = dict_to_json_sorted(payload).replace(" ", "")

    timestamp = str(int(time.time() * 1000))
    request_id = get_uuid()
    sign = get_sign(params_str, request_id, timestamp)
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.birdreport.cn",
        "Referer": "https://www.birdreport.cn/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "requestId": request_id,
        "sign": sign,
        "timestamp": timestamp,
    }

    encrypted = rsa_encrypt_long(params_str)

    response = requests.post(
        API_URL, data=encrypted, headers=headers, timeout=30, verify=False
    )
    response.raise_for_status()

    payload_json = response.json()
    encoded_data = payload_json.get("data")
    if not encoded_data:
        raise ValueError(payload_json.get("msg") or "API 未返回 data 字段")

    decoded = decrypt_response_data(encoded_data)
    parsed = json.loads(decoded)
    results = []
    for item in parsed:
        results.append(
            BirdRecord(
                chinese=item.get("taxonname", "").strip(),
                english=item.get("englishname", "").strip(),
                scientific=item.get("latinname", "").strip(),
            )
        )
    return results


def load_locations_config(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "locations" in data:
        return data["locations"]
    if isinstance(data, list):
        return data
    raise ValueError("配置文件格式错误，应为数组或包含 locations 字段的对象")


def find_location_entry(locations, identifier):
    for entry in locations:
        if entry.get("id") == identifier or entry.get("name") == identifier:
            return entry
    raise ValueError(f"在配置中找不到地点: {identifier}")


def output_results(unique_birds, output_path=None):
    lines = [f"{bird.chinese} {bird.scientific or ''}".strip() for bird in unique_birds]
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            if lines:
                f.write("\n")
    for line in lines:
        print(line)


def parse_args():
    parser = argparse.ArgumentParser(
        description="从中国观鸟记录中心抓取鸟类名单（支持 URL 或自定义参数）"
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="包含 search 参数的完整 birdreport 链接（参数模式可省略）",
    )
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--days",
        type=int,
        help="按天数回溯（如 7 表示今天往前 7 天），与 --start/--end 互斥",
    )
    parser.add_argument("--province", help="省份，如 北京市")
    parser.add_argument("--city", help="城市")
    parser.add_argument("--district", help="区县")
    parser.add_argument("--pointname", help="地点名（无别名时使用）")
    parser.add_argument(
        "--aliases",
        nargs="+",
        help="同一地点的多个搜索词，示例：--aliases 奥森北园 奥林匹克森林公园北园",
    )
    parser.add_argument("--taxonid", help="鸟种编号")
    parser.add_argument("--username", help="用户名筛选")
    parser.add_argument("--serial-id", help="serial_id 参数")
    parser.add_argument("--ctime", help="ctime 参数")
    parser.add_argument("--version", help="版本（默认 CH4）")
    parser.add_argument("--state", help="state 参数")
    parser.add_argument("--mode", type=int, help="mode 参数，默认 0")
    parser.add_argument("--taxon-month", help="taxon_month 参数")
    parser.add_argument(
        "--outside-type",
        type=int,
        help="outside_type 参数，默认 0",
    )
    parser.add_argument("--limit", type=int, help="limit 参数，默认 1500")
    parser.add_argument("--page", type=int, help="page 参数，默认 1")
    parser.add_argument(
        "--location-config",
        help="地点配置文件（JSON），可包含多个别名",
    )
    parser.add_argument(
        "--location",
        help="配置中的地点 id 或 name（需配合 --location-config 使用）",
    )
    parser.add_argument(
        "--output",
        help="将结果写入指定文件（UTF-8），同时仍会打印到 stdout",
    )
    return parser.parse_args()


def get_uuid():
    hex_digits = "0123456789abcdef"
    s = [random.choice(hex_digits) for _ in range(32)]
    s[14] = "4"
    s[19] = hex_digits[(int(s[19], 16) & 3) | 8]
    filler = s[23]
    s[8] = s[13] = s[18] = filler
    return "".join(s)


def get_sign(params, request_id, timestamp):
    import hashlib

    md5 = hashlib.md5()
    md5.update((params + request_id + timestamp).encode("utf-8"))
    return md5.hexdigest()


def rsa_encrypt_long(payload_str):
    pub = RSA.import_key(base64.b64decode(PUBLIC_KEY_B64))
    cipher = PKCS1_v1_5.new(pub)
    key_size = pub.size_in_bits() // 8
    chunk_size = key_size - 11
    data = payload_str.encode("utf-8")
    encrypted = [
        cipher.encrypt(data[i : i + chunk_size])
        for i in range(0, len(data), chunk_size)
    ]
    return base64.b64encode(b"".join(encrypted)).decode("utf-8")


def decrypt_response_data(encoded):
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv=AES_IV)
    decrypted = unpad(cipher.decrypt(base64.b64decode(encoded)), AES.block_size)
    return decrypted.decode("utf-8")


def fetch_birds_via_api(url, search_payload=None):
    ensure_crypto_available()
    if search_payload is None:
        search_payload = decode_search_param(url)
    if search_payload is None:
        print("⚠️  链接中没有找到 search 参数，无法使用 API 抓取。", file=sys.stderr)
        return None
    return fetch_birds_for_payload(search_payload)

def fetch_url(url, use_browser_headers=True):
    """
    获取 URL 内容
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    try:
        # 禁用 SSL 证书验证（仅用于中国观鸟记录中心）
        import ssl
        context = ssl._create_unverified_context()
        
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30, context=context) as response:
            # 处理 gzip 编码
            import gzip
            content = response.read()
            
            if response.headers.get('Content-Encoding') == 'gzip':
                return gzip.decompress(content).decode('utf-8')
            else:
                return content.decode('utf-8')
    except Exception as e:
        print(f"❌ 获取URL失败: {e}", file=sys.stderr)
        return None

def extract_birds_from_html(html_content):
    """
    从 HTML 中提取鸟类信息
    
    尝试多种方法：
    1. 查找 JSON 数据
    2. 解析 HTML 表格
    3. 正则表达式匹配
    """
    birds = []
    
    # 方法1：查找嵌入的 JSON 数据
    # 很多现代网站会在页面中嵌入 JSON 数据
    json_patterns = [
        r'<script[^>]*>\s*var\s+data\s*=\s*(\[.*?\]);',
        r'<script[^>]*>\s*window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        r'<script type="application/json"[^>]*>(.*?)</script>',
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, html_content, re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match)
                # 尝试从 JSON 中提取鸟类信息
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            chinese = item.get('chinese_name') or item.get('commonName') or item.get('name_cn')
                            scientific = item.get('scientific_name') or item.get('sciName') or item.get('name_sci')
                            if chinese and scientific:
                                birds.append(
                                    BirdRecord(
                                        chinese=chinese,
                                        english="",
                                        scientific=scientific,
                                    )
                                )
            except:
                pass
    
    if birds:
        return birds
    
    # 方法2：解析表格数据（使用正则表达式）
    # 查找类似 "中文名 Scientific name" 的模式
    table_pattern = r'<tr[^>]*>.*?<td[^>]*>([\u4e00-\u9fff]+)</td>.*?<td[^>]*>([A-Z][a-z]+ [a-z]+(?:\s+[a-z]+)?)</td>.*?</tr>'
    matches = re.findall(table_pattern, html_content, re.DOTALL | re.IGNORECASE)
    for chinese, scientific in matches:
        birds.append(
            BirdRecord(
                chinese=chinese.strip(),
                english="",
                scientific=scientific.strip(),
            )
        )
    
    if birds:
        return birds
    
    # 方法3：更宽松的匹配
    # 查找任何包含中文名和学名的行
    lines = html_content.split('\n')
    for line in lines:
        # 移除 HTML 标签
        clean_line = re.sub(r'<[^>]+>', ' ', line)
        # 查找中文名和学名的组合
        match = re.search(r'([\u4e00-\u9fff]{2,})\s+([A-Z][a-z]+\s+[a-z]+(?:\s+[a-z]+)?)', clean_line)
        if match:
            chinese, scientific = match.groups()
            birds.append(
                BirdRecord(
                    chinese=chinese.strip(),
                    english="",
                    scientific=scientific.strip(),
                )
            )

    return birds

def query_ebird_for_info(scientific_name, use_cache=True):
    """
    通过学名查询 eBird API 获取英文名和 speciesCode
    
    返回: (english_name, species_code, ebird_scientific_name) 或 (None, None, None)
    """
    ebird_token = os.environ.get('EBIRD_TOKEN', '')
    if not ebird_token:
        return None, None, None
    
    # 使用缓存
    cache_dir = os.path.expanduser('~/.cache/bird_memory_cards')
    os.makedirs(cache_dir, exist_ok=True)
    
    from datetime import datetime
    cache_file = os.path.join(cache_dir, f'ebird_taxonomy_{datetime.now().strftime("%Y%m")}.json')
    
    taxonomy = None
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                taxonomy = json.load(f)
        except:
            pass
    
    if not taxonomy:
        try:
            url = 'https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json'
            req = urllib.request.Request(url, headers={'X-eBirdApiToken': ebird_token})
            with urllib.request.urlopen(req, timeout=30) as response:
                taxonomy = json.loads(response.read().decode('utf-8'))
            
            # 保存到缓存
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(taxonomy, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return None, None, None
    
    # 先尝试完全匹配学名
    sci_lower = scientific_name.strip().lower()
    for item in taxonomy:
        if item.get('sciName', '').strip().lower() == sci_lower:
            return item.get('comName'), item.get('speciesCode'), item.get('sciName')
    
    return None, None, None

def main():
    args = parse_args()

    manual_flag = any(
        [
            args.start,
            args.end,
            args.days,
            args.province,
            args.city,
            args.district,
            args.pointname,
            args.aliases,
            args.taxonid,
            args.username,
            args.serial_id,
            args.ctime,
            args.version,
            args.state,
            args.mode is not None,
            args.taxon_month,
            args.outside_type is not None,
            args.limit is not None,
            args.page is not None,
        ]
    )

    payload_queries = []
    payload_mode = False

    if args.location_config:
        if not args.location:
            print("❌ 使用 --location-config 时必须通过 --location 指定地点 id 或 name", file=sys.stderr)
            sys.exit(1)
        try:
            locations = load_locations_config(args.location_config)
            entry = find_location_entry(locations, args.location)
        except Exception as exc:
            print(f"❌ 加载地点配置失败: {exc}", file=sys.stderr)
            sys.exit(1)
        base_payload = build_base_payload_from_args(args, entry)
        aliases = args.aliases or entry.get("point_aliases") or []
        payload_queries = expand_alias_payloads(base_payload, aliases)
        payload_mode = True

    if not payload_queries and manual_flag:
        base_payload = build_base_payload_from_args(args)
        payload_queries = expand_alias_payloads(base_payload, args.aliases or [])
        payload_mode = True

    if payload_queries and args.url:
        print("ℹ️  已提供参数模式，忽略 URL 输入", file=sys.stderr)

    birds = []

    if payload_mode and payload_queries:
        for idx, payload in enumerate(payload_queries, 1):
            label = payload.get("pointname") or f"自定义查询{idx}"
            print(f"🔐 {label}: 调用 API 抓取...", file=sys.stderr)
            try:
                result = fetch_birds_for_payload(payload)
            except Exception as exc:
                print(f"⚠️  {label} 抓取失败: {exc}", file=sys.stderr)
                continue
            print(f"✅ {label}: 返回 {len(result)} 条记录", file=sys.stderr)
            birds.extend(result)
        if not birds:
            print("❌ 所有自定义查询都失败或无结果", file=sys.stderr)
            sys.exit(1)
    else:
        if not args.url:
            print("❌ 请输入带 search 参数的 URL，或使用参数模式/地点配置", file=sys.stderr)
            sys.exit(1)
        url = args.url
        birds = None
        search_payload = decode_search_param(url)
        if search_payload:
            print("🔐 尝试通过 API 直接抓取鸟单...", file=sys.stderr)
            try:
                birds = fetch_birds_via_api(url, search_payload)
                if birds:
                    print(f"✅ API 返回 {len(birds)} 条记录", file=sys.stderr)
            except Exception as exc:
                print(f"⚠️  API 抓取失败，将回退到 HTML 解析: {exc}", file=sys.stderr)
                birds = None

        if not birds:
            print(f"📡 获取页面内容...", file=sys.stderr)
            html_content = fetch_url(url)

            if not html_content:
                print("❌ 无法获取页面内容", file=sys.stderr)
                sys.exit(1)

            print(f"✅ 页面内容获取成功（{len(html_content)} 字符）", file=sys.stderr)

            print(f"🔍 解析鸟类信息...", file=sys.stderr)
            birds = extract_birds_from_html(html_content)

        if not birds:
            print("⚠️  未能从页面中提取到鸟类信息", file=sys.stderr)
            print("", file=sys.stderr)
            print("可能的原因：", file=sys.stderr)
            print("  1. 页面需要登录", file=sys.stderr)
            print("  2. 页面使用了动态加载（JavaScript）", file=sys.stderr)
            print("  3. 页面结构与预期不符", file=sys.stderr)
            print("", file=sys.stderr)
            print("建议：", file=sys.stderr)
            print("  1. 手动访问页面并复制鸟类列表", file=sys.stderr)
            print("  2. 使用浏览器开发者工具查看网络请求", file=sys.stderr)
            print("  3. 检查是否有 API 端点可以直接获取数据", file=sys.stderr)
            
            # 保存 HTML 用于调试
            debug_file = '/tmp/birdreport_debug.html'
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"", file=sys.stderr)
            print(f"💾 HTML 已保存到: {debug_file}", file=sys.stderr)
            print(f"   你可以查看文件内容以了解页面结构", file=sys.stderr)
            sys.exit(1)

    print(f"✅ 找到 {len(birds)} 条记录", file=sys.stderr)
    print("", file=sys.stderr)
    
    # 去重
    unique_birds = []
    seen = set()
    for bird in birds:
        key = (bird.chinese, bird.scientific)
        if key not in seen:
            seen.add(key)
            unique_birds.append(bird)
    
    if len(unique_birds) < len(birds):
        print(f"📊 去重后: {len(unique_birds)} 种鸟类", file=sys.stderr)
        print("", file=sys.stderr)
    
    # 输出
    print("# 从中国观鸟记录中心提取的鸟类名单", file=sys.stderr)
    print("# 可以直接用 convert_to_csv.py --auto - 转换", file=sys.stderr)
    print("", file=sys.stderr)

    output_results(unique_birds, args.output)
    
    print("", file=sys.stderr)
    label = None
    if payload_mode and (args.pointname or args.location):
        label = args.pointname or args.location
    elif args.url:
        search_payload = decode_search_param(args.url)
        if search_payload:
            label = search_payload.get("pointname")
    date_str = ""
    if payload_mode:
        start = payload_queries[0].get("startTime")
        end = payload_queries[-1].get("endTime")
        if start and end:
            date_str = f"（{start}～{end}）"
    species_msg = f"{len(unique_birds)} 种"
    if label:
        print(f"✅ 完成！解析{label}{date_str}{species_msg}", file=sys.stderr)
    else:
        print(f"✅ 完成！共解析 {species_msg}", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"下一步：", file=sys.stderr)
    print(f"  python3 tools/convert_to_csv.py --auto my_birds.txt > my_birds.csv", file=sys.stderr)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
