#!/bin/bash

# 进入脚本所在的目录
cd "$(dirname "$0")"

echo "[1/3] Adding changes..."
git add .

echo "[2/3] Committing..."
msg="Auto-update $(date '+%Y-%m-%d %H:%M:%S')"
git commit -m "$msg"

echo "[3/3] Pushing to GitHub..."
git push origin main

echo "Sync Complete!"
