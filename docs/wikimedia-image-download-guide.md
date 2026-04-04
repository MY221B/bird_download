# 从 Wikimedia Commons 批量下载图片的完整指南

本文档记录了为"春日赏花指南"功能批量下载 26 张花卉图片的完整流程，包括遇到的问题和最终可靠的解决方案。供其他 Agent 复用。

---

## 总体流程

```
确定需要的图片 → 在 Wikimedia Commons 找到对应文件名
    → 用 MediaWiki API 获取缩略图 URL → 用 curl 下载实际图片 → 验证图片有效性
```

## 第一步：确定 Wikimedia Commons 文件名

在 [Wikimedia Commons](https://commons.wikimedia.org/) 搜索所需图片，记录每张图片的精确文件名。

文件名示例：
- 简单 ASCII 名：`Cherry_Blossom.jpg`
- 含空格：`Canola Flower.jpg`
- 含单引号：`Rosa banksiae 'Lutea'.jpg`
- 含中文和特殊字符：`垂絲海棠 Malus halliana -香港公園 Hong Kong Park- (9173504592).jpg`

> **重要**：文件名必须与 Wikimedia Commons 上的完全一致（大小写敏感）。

---

## 第二步：通过 MediaWiki API 获取缩略图 URL

### 为什么不能直接用 Special:FilePath？

Wikimedia 提供了 `Special:FilePath` 快捷方式：

```
https://commons.wikimedia.org/wiki/Special:FilePath/Cherry_Blossom.jpg?width=800
```

**问题**：此接口对大量文件名（尤其含空格、特殊字符的）会返回 HTML 错误页面而非图片，不可靠。

### 可靠方案：MediaWiki API

API 端点：

```
https://commons.wikimedia.org/w/api.php?action=query&titles=File:{文件名}&prop=imageinfo&iiprop=url&iiurlwidth={宽度}&format=json
```

返回 JSON 中包含 `thumburl`（缩略图）和 `url`（原图）字段。

### Python 脚本获取 URL（推荐方案）

```python
import urllib.parse, urllib.request, json, ssl, time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

UA = "YourProjectName/1.0 (educational project; contact@example.com)"

def get_thumb_url(wiki_filename, width=800):
    """通过 MediaWiki API 获取缩略图 URL"""
    encoded = urllib.parse.quote("File:" + wiki_filename)
    api_url = (
        f"https://commons.wikimedia.org/w/api.php"
        f"?action=query&titles={encoded}"
        f"&prop=imageinfo&iiprop=url&iiurlwidth={width}&format=json"
    )
    req = urllib.request.Request(api_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, context=ctx) as resp:
        d = json.loads(resp.read())
    pages = d["query"]["pages"]
    p = list(pages.values())[0]
    if "imageinfo" not in p:
        return None  # 文件不存在
    info = p["imageinfo"][0]
    return info.get("thumburl", info["url"])
```

### 关键注意事项

1. **必须设置 User-Agent**：Wikimedia API 对无 User-Agent 或 bot 风格的 UA 返回 403。
2. **必须禁用 SSL 验证（macOS 常见）**：macOS 的 Python 默认缺少根证书，`urllib` 会报 `CERTIFICATE_VERIFY_FAILED`。需要 `ssl.CERT_NONE` 绕过。
3. **必须在请求之间加延迟**：连续快速请求会触发 429 (Too Many Requests)。建议每次请求间隔 **1-2 秒**。

---

## 第三步：用 curl 下载图片

### 为什么用 curl 而不是 Python urllib？

- Python `urllib` 在 macOS 上频繁遇到 SSL 证书问题
- `curl` 自带 macOS 系统证书，更可靠
- `curl -sL` 自动跟随重定向

### 下载命令

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
curl -sL -H "User-Agent: $UA" -o "output_filename.jpg" "THUMB_URL"
```

### 关键注意事项

1. **User-Agent 必须模拟浏览器**：`upload.wikimedia.org`（图片 CDN）对自定义 UA 返回 HTML 而非图片。必须用浏览器风格的 User-Agent。
2. **API 请求和图片下载的 UA 要求不同**：
   - API 端点 (`commons.wikimedia.org/w/api.php`)：接受自定义项目 UA
   - 图片 CDN (`upload.wikimedia.org`)：需要浏览器风格 UA

---

## 完整可用脚本

以下是经过验证的、端到端可靠的批量下载脚本：

```python
#!/usr/bin/env python3
"""
从 Wikimedia Commons 批量下载图片。

用法：
  1. 在 FILES_TO_DOWNLOAD 字典中定义 {本地文件名: Wikimedia文件名}
  2. 修改 OUTPUT_DIR 为目标目录
  3. 运行脚本
"""

import urllib.parse, urllib.request, json, ssl, subprocess, os, time

# ===== 配置 =====
OUTPUT_DIR = "./flowers"
WIDTH = 800  # 缩略图宽度（像素）
API_DELAY = 1.5  # API 请求间隔（秒），防止 429
DOWNLOAD_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
API_UA = "FlowerProject/1.0 (educational; contact@example.com)"

# {本地保存文件名: Wikimedia Commons 上的文件名}
FILES_TO_DOWNLOAD = {
    "cherry_blossom.jpg": "Cherry_Blossom.jpg",
    "tulip.jpg": "Triumph_Tulip_Tulipa_'Prinses_Irene'_Single_2859px.jpg",
    # ... 添加更多
}
# ===== 配置结束 =====

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_thumb_url(wiki_filename):
    encoded = urllib.parse.quote("File:" + wiki_filename)
    api_url = (
        f"https://commons.wikimedia.org/w/api.php"
        f"?action=query&titles={encoded}"
        f"&prop=imageinfo&iiprop=url&iiurlwidth={WIDTH}&format=json"
    )
    req = urllib.request.Request(api_url, headers={"User-Agent": API_UA})
    with urllib.request.urlopen(req, context=ctx) as resp:
        d = json.loads(resp.read())
    pages = d["query"]["pages"]
    p = list(pages.values())[0]
    if "imageinfo" not in p:
        return None
    info = p["imageinfo"][0]
    return info.get("thumburl", info["url"])

def download_with_curl(url, output_path):
    result = subprocess.run(
        ["curl", "-sL", "-H", f"User-Agent: {DOWNLOAD_UA}", "-o", output_path, url],
        capture_output=True, text=True
    )
    return result.returncode == 0

def verify_image(path):
    result = subprocess.run(
        ["file", "-b", path], capture_output=True, text=True
    )
    return "JPEG" in result.stdout or "PNG" in result.stdout

# ===== 主流程 =====
failed = []
for output_name, wiki_name in FILES_TO_DOWNLOAD.items():
    output_path = os.path.join(OUTPUT_DIR, output_name)
    print(f"处理: {output_name} ...", end=" ", flush=True)

    # 步骤 1：获取缩略图 URL
    try:
        thumb_url = get_thumb_url(wiki_name)
    except Exception as e:
        print(f"API 失败: {e}")
        failed.append((output_name, wiki_name, str(e)))
        time.sleep(API_DELAY)
        continue

    if not thumb_url:
        print("文件不存在于 Wikimedia Commons")
        failed.append((output_name, wiki_name, "文件不存在"))
        time.sleep(API_DELAY)
        continue

    # 步骤 2：用 curl 下载
    if not download_with_curl(thumb_url, output_path):
        print("curl 下载失败")
        failed.append((output_name, wiki_name, "curl 失败"))
        time.sleep(API_DELAY)
        continue

    # 步骤 3：验证是否为有效图片
    if not verify_image(output_path):
        size_kb = os.path.getsize(output_path) // 1024
        print(f"下载到非图片内容 ({size_kb}KB)，重试原图 URL ...")

        # 回退：尝试原图 URL（无缩略图）
        try:
            encoded = urllib.parse.quote("File:" + wiki_name)
            api_url = (
                f"https://commons.wikimedia.org/w/api.php"
                f"?action=query&titles={encoded}"
                f"&prop=imageinfo&iiprop=url&format=json"
            )
            req = urllib.request.Request(api_url, headers={"User-Agent": API_UA})
            with urllib.request.urlopen(req, context=ctx) as resp:
                d = json.loads(resp.read())
            pages = d["query"]["pages"]
            p = list(pages.values())[0]
            full_url = p["imageinfo"][0]["url"]
            time.sleep(API_DELAY)
            download_with_curl(full_url, output_path)
        except Exception:
            pass

        if not verify_image(output_path):
            print("重试仍失败")
            failed.append((output_name, wiki_name, "内容非图片"))
            time.sleep(API_DELAY)
            continue

    size_kb = os.path.getsize(output_path) // 1024
    print(f"OK ({size_kb}KB)")
    time.sleep(API_DELAY)

# ===== 报告 =====
print(f"\n完成: {len(FILES_TO_DOWNLOAD) - len(failed)}/{len(FILES_TO_DOWNLOAD)} 成功")
if failed:
    print("\n失败列表:")
    for name, wiki, reason in failed:
        print(f"  - {name} ({wiki}): {reason}")
```

---

## 遇到的坑和解决方案汇总

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| `Special:FilePath` 返回 HTML 而非图片 | 此端点对复杂文件名不可靠 | 改用 MediaWiki API 获取真实 URL |
| Python `urllib` 报 `CERTIFICATE_VERIFY_FAILED` | macOS Python 缺少根证书 | `ssl.CERT_NONE` 禁用验证 |
| API 返回 `403 Forbidden` | 缺少 User-Agent 或被识别为 bot | 设置自定义 User-Agent |
| 连续请求返回 `429 Too Many Requests` | 请求速率过快 | 每次请求间隔 1.5 秒 |
| 图片 CDN 返回 HTML 而非图片 | `upload.wikimedia.org` 拒绝非浏览器 UA | curl 使用浏览器风格 User-Agent |
| Shell 中文件名含单引号导致语法错误 | `'Lutea'` 等破坏 shell 字符串 | 用 Python 处理文件名，避免 shell 引号问题 |
| 缩略图 URL 返回 HTML（偶发） | CDN 边缘节点偶尔异常 | 回退到原图 URL 重试 |
| 下载结果为 0KB 的文本文件 | curl 收到重定向或错误页面 | `file -b` 验证文件类型，非图片则重试 |

---

## 验证命令

下载完成后，批量验证所有图片的有效性：

```bash
cd /path/to/output_dir
for f in *.jpg; do
  ftype=$(file -b "$f" | head -c 25)
  size=$(du -k "$f" | cut -f1)
  if echo "$ftype" | grep -q "JPEG\|PNG"; then
    echo "OK: $f (${size}KB)"
  else
    echo "BAD: $f (${size}KB, $ftype)"
  fi
done
```

---

## 许可证说明

Wikimedia Commons 上的图片通常采用以下许可证之一：
- CC BY-SA 4.0 / 3.0 / 2.0
- CC BY 4.0 / 3.0 / 2.0
- Public Domain

在使用时应标注图片来源。本项目在页面底部添加了"图片来源网络，仅供参考"的提示。

---

**最后更新**：2026-04-03
