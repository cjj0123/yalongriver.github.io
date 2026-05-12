#!/bin/bash

# 进入脚本所在的目录
cd "$(dirname "$0")"

# 记录开始运行时间
echo "------------------------------------------"
echo "Job started at: $(date)"

# 运行爬虫
# 如果环境中有多个 python，建议使用绝对路径，例如 /usr/local/bin/python3
# 这里先尝试直接用 python3
python3 scraper.py

echo "Job finished at: $(date)"
echo "------------------------------------------"
