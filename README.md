# 雅砻江水位监测维护说明

## 定时任务

本机使用 launchd 运行定时抓取任务：

- 配置文件：`~/Library/LaunchAgents/com.jijunchen.yalongriver.scraper.plist`
- 执行脚本：`run_scraper.sh`
- 日志文件：`/tmp/yalongriver_scrape_stdout.log`、`/tmp/yalongriver_scrape_stderr.log`
- 当前计划时间：每天 `07:00`、`10:30`、`11:30`

查看任务状态：

```bash
launchctl print gui/$(id -u)/com.jijunchen.yalongriver.scraper
```

## GitHub 推送和代理

这个项目的 GitHub Pages 更新依赖 `git push origin main`。本机访问 GitHub 需要走本地代理：

- 代理程序：`mihomo`
- 代理地址：当前使用 `127.0.0.1:7890`，并兼容 `127.0.0.1:17890`
- macOS 系统代理会使用这个端口，但 launchd 定时任务和终端里的 Git 命令不会自动继承系统代理。

因此 `run_scraper.sh` 会依次检测 `127.0.0.1:7890` 和 `127.0.0.1:17890`。如果端口可用，脚本会导出对应的代理环境变量。当前配置为：

```bash
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
ALL_PROXY=socks5://127.0.0.1:7890
```

本仓库 Git 也配置为走同一个代理，并使用 HTTP/1.1：

```bash
git config --local http.proxy http://127.0.0.1:7890
git config --local https.proxy http://127.0.0.1:7890
git config --local http.version HTTP/1.1
```

如果以后看到 `git push` 报 `Error in the HTTP2 framing layer`、`Failed to connect to github.com port 443`、`Operation timed out`，不要先怀疑 GitHub 权限或代码问题。优先检查：

```bash
lsof -nP -iTCP:7890 -sTCP:LISTEN
curl -I -x http://127.0.0.1:7890 --connect-timeout 10 --max-time 30 https://github.com
git config --local --get-regexp '^(http|https)\.'
```

如果两个代理端口都不可用，自动任务会记录直连提示，随后直连 GitHub 可能失败。

## 雪球登录态

雪球接口经常需要登录态，否则会被 WAF 或滑块验证拦截。脚本支持通过本地环境变量读取 Cookie：

```bash
XUEQIU_COOKIE='xq_a_token=...; xq_id_token=...; ...'
```

请把它写在项目根目录的 `.env.local` 中。该文件已加入 `.gitignore`，不要提交到 GitHub。`run_scraper.sh` 每次运行都会自动加载 `.env.local`。

脚本会优先读取 `xueqiu_posts/` 中已经缓存的纬班长帖子；如果通过登录态成功抓到新帖，会自动缓存为 `日期-帖子ID.txt`。网页中的雪球来源链接统一指向雪球原帖，而不是本机缓存文件路径。
