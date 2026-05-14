## Learned User Preferences

- Never use rm -rf

## Learned Workspace Facts

## Cursor Cloud Agent

Cloud Agent 启动时会执行仓库根目录 `.cursor/environment.json` 里的 `install` 命令（见 [Cursor Cloud 环境文档](https://cursor.com/docs/cloud-agent/setup.md)）。本仓库对应脚本为 `.cursor/cloud_agent_install.sh`，会依次：`git submodule update --init --recursive`、`pip install --user -r requirements.txt`（含 `requests`、`pycryptodome`、`cloudinary`）、`npm ci --prefix feather-flash-quiz`，并校验 `feather-flash-quiz/scripts/generate-location-birds-manifest.js` 存在。

- 子模块若为私有仓库，必须在 Cloud Agents 环境配置里允许访问 `github.com/MY221B/feather-flash-quiz`（本仓库已在 `environment.json` 的 `repositoryDependencies` 中声明），否则 `git submodule update` 会失败。
- `tools/v2_weekly_refresh_and_push.sh` 在推送子模块前会读取 Secret `FEATHER_FLASH_QUIZ_TOKEN`（若已配置）并重写子模块 `origin`，与安装阶段的克隆凭据分开，避免把 token 写进安装脚本或重复写入全局配置。
- 周报脚本还需要 `config/ebird_token.sh`、Cloudinary 等与抓取/上传相关的密钥；请在同一环境的 Secrets 中配置，并在需要推送时保证 Git `user.name` / `user.email` 可用（全局或子模块内）。