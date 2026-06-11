#!/bin/bash
set -euo pipefail

# 进入脚本所在的目录
cd "$(dirname "$0")"

# launchd 的默认 PATH 很短，直接指定带有 playwright 的解释器
PYTHON_BIN="${PYTHON_BIN:-/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11}"
LOCK_DIR="/tmp/yalongriver_scraper.lock"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

cleanup() {
  local exit_code=$?
  rmdir "$LOCK_DIR" 2>/dev/null || true
  log "Job finished with exit code: $exit_code"
  echo "------------------------------------------"
}

trap cleanup EXIT

# 记录开始运行时间
echo "------------------------------------------"
log "Job started"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "另一个爬虫任务仍在运行，本次跳过，避免重复写库。"
  exit 75
fi

if [ ! -x "$PYTHON_BIN" ]; then
  log "Python 不存在或不可执行: $PYTHON_BIN"
  exit 78
fi

if ! "$PYTHON_BIN" -c "from playwright.sync_api import sync_playwright" >/dev/null 2>&1; then
  log "当前 Python 缺少 Playwright: $PYTHON_BIN"
  log "可用这个命令修复: $PYTHON_BIN -m pip install playwright && $PYTHON_BIN -m playwright install chromium"
  exit 78
fi

# 运行爬虫
export GIT_TERMINAL_PROMPT=0
export PYTHONUNBUFFERED=1
if nc -z 127.0.0.1 17890 >/dev/null 2>&1; then
  export HTTP_PROXY="http://127.0.0.1:17890"
  export HTTPS_PROXY="http://127.0.0.1:17890"
  export ALL_PROXY="socks5://127.0.0.1:17890"
  export http_proxy="$HTTP_PROXY"
  export https_proxy="$HTTPS_PROXY"
  export all_proxy="$ALL_PROXY"
  log "已启用本地代理: 127.0.0.1:17890"
else
  log "本地代理 127.0.0.1:17890 不可用，将直接访问网络。"
fi
"$PYTHON_BIN" scraper.py
