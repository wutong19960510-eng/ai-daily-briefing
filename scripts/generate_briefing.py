#!/usr/bin/env python3
"""每日 AI 简报生成器 — 搜索→结构化JSON→HTML→GitHub Pages→Notion→Bark"""

import os
import json
import datetime
import urllib.request
import html as html_module

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
BARK_URL = os.environ["BARK_URL"]
BRIEFING_PAGE_ID = os.environ.get("NOTION_BRIEFING_PAGE_ID", "335930ef-6924-81c0-830e-e8ada800a5c0")
PAGES_BASE_URL = os.environ.get("PAGES_BASE_URL", "https://wutong19960510-eng.github.io/ai-daily-briefing")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DOCS_DIR = os.path.join(REPO_ROOT, "docs")


def load_builders():
    with open(os.path.join(SCRIPT_DIR, "builders.json"), "r") as f:
        return json.load(f)


def call_claude(messages, tools=None, model="claude-haiku-4-5-20251001"):
    body = {"model": model, "max_tokens": 8192, "messages": messages}
    if tools:
        body["tools"] = tools
    data = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    }
    if tools:
        headers["anthropic-beta"] = "web-search-2025-03-05"
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_claude_with_search(prompt):
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}]
    messages = [{"role": "user", "content": prompt}]
    round_count = 0
    while True:
        round_count += 1
        print(f"   [API call #{round_count}]")
        result = call_claude(messages, tools=tools)
        stop_reason = result.get("stop_reason", "")
        content_blocks = result.get("content", [])
        print(f"   [stop_reason: {stop_reason}, blocks: {len(content_blocks)}]")

        if stop_reason == "end_turn":
            text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
            return "\n".join(text_parts)

        messages.append({"role": "assistant", "content": content_blocks})
        tool_results = []
        for b in content_blocks:
            if b.get("type") == "tool_use":
                tool_results.append({"type": "tool_result", "tool_use_id": b["id"], "content": "done"})
        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        else:
            text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
            return "\n".join(text_parts)


def search_and_get_json(builders_data):
    today = datetime.date.today().strftime("%Y-%m-%d")
    builder_names = ", ".join(b["name"] for b in builders_data["builders"])
    podcast_names = ", ".join(p["name"] for p in builders_data["podcasts"])

    prompt = f"""今天是 {today}。你是 AI 行业简报助手。

搜索以下 AI 领域关键人物最近 24 小时的重要动态：
{builder_names}

同时关注播客新内容：{podcast_names}
同时关注 Anthropic、OpenAI、Google DeepMind 官方博客。

请输出 **严格 JSON**（不要 markdown 代码块，不要额外文字），格式如下：

{{
  "date": "{today}",
  "trend_summary": "一句话总结今日 AI 趋势（中文）",
  "sections": [
    {{
      "id": "breaking",
      "title": "今日要闻",
      "icon": "🔥",
      "items": [
        {{
          "headline": "标题（中文）",
          "summary": "2-3句摘要（中文）",
          "source_name": "来源名称（如 X/Twitter, Anthropic Blog）",
          "source_url": "https://原始链接",
          "author": "作者名"
        }}
      ]
    }},
    {{
      "id": "builders",
      "title": "Builder 动态",
      "icon": "👤",
      "items": [...]
    }},
    {{
      "id": "media",
      "title": "播客与博客",
      "icon": "🎙️",
      "items": [...]
    }}
  ]
}}

规则：
- 只收录有真实搜索结果支撑的内容，不要编造
- source_url 必须是真实可访问的链接
- 没有动态的人不要硬凑，跳过
- 每个 section 的 items 可以为空数组
- headline 和 summary 用中文"""

    raw = call_claude_with_search(prompt)

    # 清理可能的 markdown 包裹
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"   [JSON parse error: {e}]")
        print(f"   [Raw output: {text[:500]}]")
        # 回退：用纯文本包装
        return {
            "date": today,
            "trend_summary": "简报生成异常，请查看原始内容",
            "sections": [{
                "id": "raw", "title": "原始内容", "icon": "📄",
                "items": [{"headline": "简报内容", "summary": raw[:2000], "source_name": "", "source_url": "", "author": ""}]
            }]
        }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 简报 · {date}</title>
<style>
  :root {{
    --bg: #0a0a0f;
    --surface: #14141f;
    --card: #1a1a2e;
    --card-hover: #222240;
    --border: #2a2a45;
    --text: #e0e0f0;
    --text-secondary: #8888aa;
    --accent: #6c5ce7;
    --accent-light: #a29bfe;
    --fire: #fd7272;
    --green: #55efc4;
    --yellow: #ffeaa7;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.7;
    min-height: 100vh;
  }}
  .container {{
    max-width: 800px;
    margin: 0 auto;
    padding: 24px 16px 60px;
  }}
  /* Header */
  .header {{
    text-align: center;
    padding: 40px 0 32px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 32px;
  }}
  .header-label {{
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 3px;
    color: var(--accent-light);
    margin-bottom: 8px;
  }}
  .header h1 {{
    font-size: 28px;
    font-weight: 700;
    margin-bottom: 12px;
    background: linear-gradient(135deg, var(--accent-light), var(--green));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }}
  .header .date {{
    font-size: 14px;
    color: var(--text-secondary);
  }}
  /* Trend summary */
  .trend {{
    background: linear-gradient(135deg, var(--accent) 0%, #3d3d8f 100%);
    border-radius: 16px;
    padding: 20px 24px;
    margin-bottom: 36px;
    font-size: 16px;
    line-height: 1.8;
    position: relative;
    overflow: hidden;
  }}
  .trend::before {{
    content: '💡';
    font-size: 48px;
    position: absolute;
    right: 16px;
    top: 50%;
    transform: translateY(-50%);
    opacity: 0.15;
  }}
  .trend p {{ position: relative; z-index: 1; }}
  /* Section */
  .section {{
    margin-bottom: 36px;
  }}
  .section-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }}
  .section-icon {{
    font-size: 22px;
  }}
  .section-title {{
    font-size: 18px;
    font-weight: 600;
  }}
  .section-count {{
    font-size: 12px;
    background: var(--border);
    color: var(--text-secondary);
    padding: 2px 8px;
    border-radius: 10px;
  }}
  /* Cards */
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 12px;
    transition: all 0.2s ease;
    cursor: pointer;
    text-decoration: none;
    display: block;
    color: inherit;
  }}
  .card:hover {{
    background: var(--card-hover);
    border-color: var(--accent);
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(108, 92, 231, 0.15);
  }}
  .card-headline {{
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 8px;
    color: var(--text);
  }}
  .card-summary {{
    font-size: 14px;
    color: var(--text-secondary);
    line-height: 1.7;
    margin-bottom: 12px;
  }}
  .card-meta {{
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 12px;
    color: var(--text-secondary);
  }}
  .card-source {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--surface);
    padding: 4px 10px;
    border-radius: 6px;
  }}
  .card-source img {{
    width: 14px;
    height: 14px;
    border-radius: 3px;
  }}
  .card-author {{
    color: var(--accent-light);
  }}
  .card-link-icon {{
    margin-left: auto;
    color: var(--accent-light);
    font-size: 16px;
  }}
  /* Empty */
  .empty {{
    text-align: center;
    padding: 24px;
    color: var(--text-secondary);
    font-size: 14px;
  }}
  /* Footer */
  .footer {{
    text-align: center;
    padding-top: 32px;
    border-top: 1px solid var(--border);
    font-size: 12px;
    color: var(--text-secondary);
  }}
  .footer a {{
    color: var(--accent-light);
    text-decoration: none;
  }}
  /* Archive link */
  .archive-nav {{
    text-align: center;
    margin-bottom: 24px;
  }}
  .archive-nav a {{
    color: var(--accent-light);
    text-decoration: none;
    font-size: 13px;
    padding: 6px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    transition: all 0.2s;
  }}
  .archive-nav a:hover {{
    background: var(--card);
    border-color: var(--accent);
  }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="header-label">Follow Builders, Not Influencers</div>
    <h1>AI 简报</h1>
    <div class="date">{date}</div>
  </div>

  <div class="trend">
    <p>{trend_summary}</p>
  </div>

  <div class="archive-nav">
    <a href="index.html">📚 历史简报</a>
  </div>

  {sections_html}

  <div class="footer">
    <p>Powered by Claude · 数据来源: Web Search</p>
    <p style="margin-top:4px"><a href="https://github.com/zarazhangrui/follow-builders">Follow Builders</a> 灵感</p>
  </div>
</div>
</body>
</html>"""


def get_favicon_url(source_url):
    """从 URL 提取 favicon"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(source_url)
        if parsed.hostname:
            return f"https://www.google.com/s2/favicons?domain={parsed.hostname}&sz=32"
    except Exception:
        pass
    return ""


def render_html(briefing_data):
    date = html_module.escape(briefing_data.get("date", ""))
    trend = html_module.escape(briefing_data.get("trend_summary", ""))

    sections_html = ""
    for section in briefing_data.get("sections", []):
        icon = html_module.escape(section.get("icon", ""))
        title = html_module.escape(section.get("title", ""))
        items = section.get("items", [])

        cards_html = ""
        if not items:
            cards_html = '<div class="empty">暂无更新</div>'
        else:
            for item in items:
                headline = html_module.escape(item.get("headline", ""))
                summary = html_module.escape(item.get("summary", ""))
                source_name = html_module.escape(item.get("source_name", ""))
                source_url = item.get("source_url", "")
                author = html_module.escape(item.get("author", ""))
                favicon = get_favicon_url(source_url) if source_url else ""

                favicon_img = f'<img src="{html_module.escape(favicon)}" alt="" onerror="this.style.display=\'none\'">' if favicon else ""
                author_span = f'<span class="card-author">@{author}</span>' if author else ""

                tag = "a" if source_url else "div"
                href = f'href="{html_module.escape(source_url)}" target="_blank" rel="noopener"' if source_url else ""
                link_icon = '<span class="card-link-icon">↗</span>' if source_url else ""

                cards_html += f"""<{tag} class="card" {href}>
  <div class="card-headline">{headline}</div>
  <div class="card-summary">{summary}</div>
  <div class="card-meta">
    <span class="card-source">{favicon_img}{source_name}</span>
    {author_span}
    {link_icon}
  </div>
</{tag}>
"""

        sections_html += f"""<div class="section">
  <div class="section-header">
    <span class="section-icon">{icon}</span>
    <span class="section-title">{title}</span>
    <span class="section-count">{len(items)}</span>
  </div>
  {cards_html}
</div>
"""

    return HTML_TEMPLATE.format(
        date=date,
        trend_summary=trend,
        sections_html=sections_html,
    )


INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 简报 · 归档</title>
<style>
  :root {{
    --bg: #0a0a0f; --surface: #14141f; --card: #1a1a2e;
    --border: #2a2a45; --text: #e0e0f0; --text-secondary: #8888aa;
    --accent-light: #a29bfe; --green: #55efc4;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background:var(--bg); color:var(--text); min-height:100vh; }}
  .container {{ max-width:600px; margin:0 auto; padding:40px 16px; }}
  h1 {{ text-align:center; font-size:24px; margin-bottom:8px;
       background:linear-gradient(135deg,var(--accent-light),var(--green));
       -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
  .subtitle {{ text-align:center; color:var(--text-secondary); font-size:13px; margin-bottom:32px; }}
  .list a {{
    display:block; padding:14px 18px; margin-bottom:8px;
    background:var(--card); border:1px solid var(--border); border-radius:10px;
    color:var(--text); text-decoration:none; font-size:15px;
    transition: all 0.2s;
  }}
  .list a:hover {{ border-color:var(--accent-light); transform:translateX(4px); }}
  .list a span {{ color:var(--text-secondary); font-size:13px; float:right; }}
</style>
</head>
<body>
<div class="container">
  <h1>📡 AI 简报归档</h1>
  <div class="subtitle">Follow Builders, Not Influencers</div>
  <div class="list">
    {links}
  </div>
</div>
</body>
</html>"""


def save_html(briefing_data, html_content):
    os.makedirs(DOCS_DIR, exist_ok=True)
    date = briefing_data["date"]
    filepath = os.path.join(DOCS_DIR, f"{date}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"   HTML saved: {filepath}")

    # 更新 index.html（列出所有简报）
    html_files = sorted(
        [f for f in os.listdir(DOCS_DIR) if f.endswith(".html") and f != "index.html"],
        reverse=True
    )
    links = ""
    for fname in html_files:
        d = fname.replace(".html", "")
        links += f'    <a href="{fname}">AI 简报 · {d} <span>→</span></a>\n'

    index_html = INDEX_TEMPLATE.format(links=links)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)
    print("   index.html updated")

    return f"{PAGES_BASE_URL}/{date}.html"


def create_notion_page(title, briefing_data):
    """简化版 Notion 存档 — 存趋势总结 + 链接"""
    trend = briefing_data.get("trend_summary", "")
    page_url = f"{PAGES_BASE_URL}/{briefing_data['date']}.html"

    children = [
        {"object": "block", "type": "bookmark", "bookmark": {"url": page_url}},
        {"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": f"💡 {trend}"}}]
        }},
    ]

    # 每个 section 的要点
    for section in briefing_data.get("sections", []):
        icon = section.get("icon", "")
        stitle = section.get("title", "")
        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": f"{icon} {stitle}"}}]}
        })
        for item in section.get("items", [])[:10]:
            headline = item.get("headline", "")
            children.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": headline}}]}
            })

    body = {
        "parent": {"page_id": BRIEFING_PAGE_ID},
        "icon": {"type": "emoji", "emoji": "📰"},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
        "children": children[:100],
    }

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return result.get("url", "")


def send_bark(title, body, url=None):
    bark_base = BARK_URL.rstrip("/")
    payload = {"title": title, "body": body, "level": "timeSensitive"}
    if url:
        payload["url"] = url
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(bark_base, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    print("📡 开始生成每日 AI 简报...")

    builders_data = load_builders()
    print(f"   已加载 {len(builders_data['builders'])} 位 builder")

    print("   正在搜索并生成结构化简报...")
    briefing_data = search_and_get_json(builders_data)
    print(f"   简报数据: {len(briefing_data.get('sections', []))} 个板块")

    print("   正在渲染 HTML...")
    html_content = render_html(briefing_data)
    page_url = save_html(briefing_data, html_content)
    print(f"   页面地址: {page_url}")

    today = briefing_data.get("date", datetime.date.today().strftime("%Y-%m-%d"))
    title = f"AI 简报 · {today}"

    print("   正在写入 Notion...")
    notion_url = create_notion_page(title, briefing_data)
    print(f"   Notion: {notion_url}")

    print("   正在推送 Bark...")
    send_bark("📡 AI 简报已更新", title, url=page_url)
    print("   推送完成")

    print("✅ 全部完成")


if __name__ == "__main__":
    main()
