#!/usr/bin/env python3
"""PostToolUse hook: 我（AI）改完文件后自动检查语法/格式。"""
import json, sys, subprocess

data = json.load(sys.stdin)
file_path = data.get("tool_input", {}).get("file_path", "")

if file_path.endswith(".py"):
    result = subprocess.run(
        ["python3", "-m", "py_compile", file_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"❌ 语法错误: {result.stderr.strip()}")
        sys.exit(1)

elif file_path.endswith(".json") and "configs/" in file_path:
    try:
        with open(file_path) as f:
            json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"❌ JSON 格式错误: {e}")
        sys.exit(1)
