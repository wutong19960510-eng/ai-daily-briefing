#!/usr/bin/env python3
"""每日 AI 简报生成器 — 搜索 AI builder 动态，生成中文简报，存入 Notion，推送 Bark"""

import os
import json
import datetime
import urllib.request
import urllib.parse

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
BARK_URL = os.environ["BARK_URL"]
BRIEFING_PAGE_ID = os.environ.get("NOTION_BRIEFING_PAGE_ID", "335930ef-6924-81c0-830e-e8ada800a5c0")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_builders():
    with open(os.path.join(SCRIPT_DIR, "builders.json"), "r") as f:
        return json.load(f)


def call_claude(messages, tools=None, model="claude-haiku-4-5-20251001"):
    """调用 Anthropic Messages API"""
    body = {
        "model": model,
        "max_tokens": 4096,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_claude_with_search(prompt):
    """调用 Claude 并启用 web_search 工具，自动处理多轮调用"""
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}]
    messages = [{"role": "user", "content": prompt}]

    # 循环处理 tool_use 响应
    while True:
        result = call_claude(messages, tools=tools)
        stop_reason = result.get("stop_reason", "")

        if stop_reason == "end_turn":
            # 提取最终文本
            text_parts = []
            for block in result.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block["text"])
            return "\n".join(text_parts)

        # 如果还有 tool_use，把 assistant 回复和 tool results 加入消息
        assistant_content = result.get("content", [])
        messages.append({"role": "assistant", "content": assistant_content})

        # 构建 tool results
        tool_results = []
        for block in assistant_content:
            if block.get("type") == "web_search_tool_result":
                # web_search 结果已经内联，不需要额外处理
                continue
            if block.get("type") == "tool_use":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": "Search completed.",
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        else:
            # 没有需要处理的 tool_use，直接返回文本
            text_parts = []
            for block in result.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block["text"])
            return "\n".join(text_parts)


def generate_briefing_content(builders_data):
    """生成简报内容"""
    today = datetime.date.today().strftime("%Y-%m-%d")
    builder_names = ", ".join(b["name"] for b in builders_data["builders"])
    podcast_names = ", ".join(p["name"] for p in builders_data["podcasts"])

    prompt = f"""今天是 {today}。你是一个 AI 行业简报助手。

请搜索以下 AI 领域关键人物最近 24 小时的重要动态、观点和发布：
{builder_names}

同时关注以下播客是否有新内容：
{podcast_names}

同时关注 Anthropic、OpenAI、Google DeepMind 官方博客的最新文章。

请生成一份中文简报，格式要求：
1. 标题：AI 简报 · {today}
2. 分为几个板块：
   - 🔥 今日要闻（最重要的 1-3 条）
   - 👤 Builder 动态（按人分列重要发言/发布）
   - 🎙️ 播客/博客更新（如有）
   - 💡 一句话总结今日趋势
3. 每条附上信息来源（谁说的/哪篇文章）
4. 语言：中文，简洁有力，不要废话
5. 如果某人最近 24 小时没有重要动态，不要硬凑，跳过即可"""

    return call_claude_with_search(prompt)


def create_notion_page(title, content):
    """在 Notion 简报页面下创建子页面"""
    # 将内容按段落拆分为 Notion blocks
    paragraphs = content.split("\n")
    children = []
    for para in paragraphs:
        text = para.strip()
        if not text:
            continue
        # 检测标题
        if text.startswith("# "):
            children.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": text[2:]}}]
                },
            })
        elif text.startswith("## "):
            children.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": text[3:]}}]
                },
            })
        elif text.startswith("### "):
            children.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": text[4:]}}]
                },
            })
        elif text.startswith("- ") or text.startswith("* "):
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": text[2:]}}]
                },
            })
        else:
            # 普通段落，Notion rich_text 限制 2000 字符
            while text:
                chunk = text[:2000]
                text = text[2000:]
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": chunk}}]
                    },
                })

    body = {
        "parent": {"page_id": BRIEFING_PAGE_ID},
        "icon": {"type": "emoji", "emoji": "📰"},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
        "children": children[:100],  # Notion 限制每次最多 100 个 block
    }

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/pages",  # placeholder, will fix
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
        },
    )
    # Fix: use Notion API
    req.full_url = "https://api.notion.com/v1/pages"
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return result.get("url", "")


def send_bark(title, body):
    """发送 Bark 推送"""
    url = BARK_URL.rstrip("/")
    payload = json.dumps({
        "title": title,
        "body": body,
        "level": "timeSensitive",
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    print("📡 开始生成每日 AI 简报...")

    # 1. 加载 builders 列表
    builders_data = load_builders()
    print(f"   已加载 {len(builders_data['builders'])} 位 builder")

    # 2. 生成简报
    print("   正在搜索最新动态并生成简报...")
    content = generate_briefing_content(builders_data)
    print("   简报生成完成")

    # 3. 存入 Notion
    today = datetime.date.today().strftime("%Y-%m-%d")
    title = f"AI 简报 · {today}"
    print(f"   正在写入 Notion: {title}")
    notion_url = create_notion_page(title, content)
    print(f"   Notion 页面: {notion_url}")

    # 4. 推送 Bark
    print("   正在推送 Bark 通知...")
    send_bark("📡 AI 简报已更新", f"{title}\n打开 Notion 查看")
    print("   推送完成")

    print("✅ 全部完成")


if __name__ == "__main__":
    main()
