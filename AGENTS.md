## Learned User Preferences

- Never use rm -rf

## Learned Workspace Facts

## Cloud Agent

本地测试和记忆卡网站不需要密钥。下载图片、上传 Cloudinary、微信推送才需要密钥。

- `feather-flash-quiz` 是 git 子模块。前端命令前先执行 `git submodule update --init --recursive feather-flash-quiz`。
- Python：`python3 -m pip install --user -r requirements.txt`，然后 `python3 -m playwright install-deps chromium` 和 `python3 -m playwright install chromium`。用户级脚本在 `~/.local/bin`，不在默认 PATH 上；调用 `python3 -m playwright`。
- 前端在 `feather-flash-quiz`：`npm ci`，再 `npm run generate:web-data`。开发服务器是 `npx vite --host :: --port 8080`（http://127.0.0.1:8080/）。`npm run dev` 会先重新生成地点数据。
- 测试：仓库根目录 `python3 -m unittest discover -s tests`；前端目录 `npm test`。类型检查：`npx tsc -p tsconfig.app.json --noEmit`。`npm run lint` 会因仓库里既有的 ESLint 问题失败。
- 可选密钥：从 `config/ebird_token.sh.example` 复制 `config/ebird_token.sh`，从 `.cloudinary_secrets.example` 复制 `.cloudinary_secrets`，从 `config/wxpusher.json.example` 复制 `config/wxpusher.json`。高德距离是前端 `.env` 里的可选项。记忆卡使用 JSON 中已有的图片地址。