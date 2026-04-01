#!/usr/bin/env python3
"""每日 AI 简报生成器 — 搜索→JSON→HTML→GitHub Pages→Bark"""

import os
import json
import datetime
import urllib.request
import html as html_module

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
BARK_URL = os.environ["BARK_URL"]
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

    # Step 1: 搜索
    search_prompt = f"""今天是 {today}。搜索以下 AI 领域关键人物和机构的最新动态（最近几天都可以）：

人物：{builder_names}
播客：{podcast_names}
博客：Anthropic、OpenAI、Google DeepMind

请列出你搜索到的所有重要信息：
- 谁说了什么/发布了什么
- **具体的文章/帖子/视频的完整 URL**（不要只给域名首页，要给到具体页面）
- 来源类型（X/Twitter、博客、YouTube 等）

用中文总结。每条必须附带具体 URL。"""

    print("   Step 1: 搜索...")
    raw_info = call_claude_with_search(search_prompt)
    print(f"   搜索结果: {len(raw_info)} chars")

    # Step 2: 格式化 JSON
    format_prompt = f"""将以下 AI 行业信息整理为严格 JSON。

原始信息：
---
{raw_info}
---

直接输出 JSON（不要 ```，不要额外文字）：

{{
  "date": "{today}",
  "trend_summary": "一句话总结（中文，20字以内）",
  "sections": [
    {{
      "id": "breaking",
      "title": "今日要闻",
      "icon": "🔥",
      "items": [
        {{
          "headline": "标题（中文）",
          "summary": "2-3句摘要（中文）",
          "source_name": "来源",
          "source_url": "具体文章/帖子的完整URL，不是域名首页",
          "author": "作者名"
        }}
      ]
    }},
    {{
      "id": "builders",
      "title": "Builder 动态",
      "icon": "👤",
      "items": [同上]
    }},
    {{
      "id": "media",
      "title": "播客与博客",
      "icon": "🎙️",
      "items": [同上]
    }}
  ]
}}

重要：
- source_url 必须是具体页面链接（如 https://x.com/karpathy/status/xxx），绝对不能是首页（如 https://x.com）
- 如果原始信息中没有具体链接，source_url 设为空字符串 ""
- breaking 放 1-3 条最重要的
- 没有内容的 section items 设为 []"""

    print("   Step 2: JSON...")
    raw_json = call_claude([{"role": "user", "content": format_prompt}])
    text_parts = [b["text"] for b in raw_json.get("content", []) if b.get("type") == "text"]
    text = "\n".join(text_parts).strip()

    if text.startswith("```"):
        first_nl = text.find("\n")
        text = text[first_nl + 1:] if first_nl != -1 else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    print(f"   JSON: {len(text)} chars")

    # 尝试解析，失败则让 Claude 修复
    for attempt in range(3):
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            if attempt < 2:
                print(f"   [JSON error attempt {attempt+1}: {e}] fixing...")
                fix_result = call_claude([{"role": "user", "content": f"以下 JSON 有语法错误，请修复并只输出正确的 JSON（不要 ```）：\n\n{text}"}])
                text = "\n".join(b["text"] for b in fix_result.get("content", []) if b.get("type") == "text").strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            else:
                print(f"   [JSON failed after 3 attempts: {e}]")
                # 最终回退：用原始搜索内容拆段展示
                paragraphs = raw_info.split("\n")
                items = []
                for p in paragraphs:
                    p = p.strip()
                    if len(p) > 10:
                        items.append({"headline": p[:50], "summary": p, "source_name": "", "source_url": "", "author": ""})
                    if len(items) >= 15:
                        break
                return {
                    "date": today,
                    "trend_summary": "AI 行业每日动态",
                    "sections": [{"id": "all", "title": "今日动态", "icon": "📡", "items": items}]
                }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 简报 · {date}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", "PingFang SC", sans-serif;
    background: #f5f5f7;
    color: #1d1d1f;
    line-height: 1.75;
    -webkit-font-smoothing: antialiased;
  }}
  .container {{
    max-width: 720px;
    margin: 0 auto;
    padding: 20px 16px 60px;
  }}
  /* Header */
  .header {{
    text-align: center;
    padding: 36px 0 28px;
    margin-bottom: 24px;
  }}
  .header-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 2.5px;
    color: #6e6e73;
    margin-bottom: 10px;
  }}
  .header h1 {{
    font-size: 32px;
    font-weight: 700;
    color: #1d1d1f;
    margin-bottom: 6px;
  }}
  .header .date {{
    font-size: 15px;
    color: #86868b;
  }}
  /* Trend */
  .trend {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 16px;
    padding: 22px 24px;
    margin-bottom: 32px;
    color: #fff;
    font-size: 17px;
    font-weight: 500;
    line-height: 1.7;
    position: relative;
  }}
  .trend::after {{
    content: '💡';
    font-size: 40px;
    position: absolute;
    right: 20px;
    top: 50%;
    transform: translateY(-50%);
    opacity: 0.2;
  }}
  /* Section */
  .section {{
    margin-bottom: 28px;
  }}
  .section-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 14px;
  }}
  .section-icon {{
    font-size: 20px;
  }}
  .section-title {{
    font-size: 18px;
    font-weight: 600;
    color: #1d1d1f;
  }}
  .section-count {{
    font-size: 11px;
    background: #e8e8ed;
    color: #6e6e73;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 500;
  }}
  /* Cards */
  .card {{
    background: #fff;
    border-radius: 14px;
    padding: 18px 20px;
    margin-bottom: 10px;
    text-decoration: none;
    display: block;
    color: inherit;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    transition: all 0.2s ease;
    border: 1px solid transparent;
  }}
  a.card:hover {{
    box-shadow: 0 4px 16px rgba(0,0,0,0.1);
    border-color: #667eea;
    transform: translateY(-1px);
  }}
  .card-headline {{
    font-size: 16px;
    font-weight: 600;
    color: #1d1d1f;
    margin-bottom: 6px;
    line-height: 1.5;
  }}
  .card-summary {{
    font-size: 14px;
    color: #424245;
    line-height: 1.75;
    margin-bottom: 12px;
  }}
  .card-meta {{
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 12px;
    color: #86868b;
    flex-wrap: wrap;
  }}
  .card-source {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: #f5f5f7;
    padding: 3px 10px;
    border-radius: 6px;
    font-weight: 500;
  }}
  .card-source img {{
    width: 14px;
    height: 14px;
    border-radius: 3px;
  }}
  .card-author {{
    color: #667eea;
    font-weight: 500;
  }}
  .card-link-icon {{
    margin-left: auto;
    color: #667eea;
    font-size: 14px;
    font-weight: 600;
  }}
  .no-link {{
    cursor: default;
  }}
  /* Empty */
  .empty {{
    text-align: center;
    padding: 20px;
    color: #86868b;
    font-size: 14px;
    background: #fff;
    border-radius: 14px;
  }}
  /* Footer */
  .footer {{
    text-align: center;
    padding-top: 28px;
    font-size: 12px;
    color: #86868b;
  }}
  .footer a {{ color: #667eea; text-decoration: none; }}
  /* Archive */
  .archive-nav {{
    text-align: center;
    margin-bottom: 20px;
  }}
  .archive-nav a {{
    color: #667eea;
    text-decoration: none;
    font-size: 13px;
    padding: 6px 16px;
    border: 1px solid #e8e8ed;
    border-radius: 8px;
    font-weight: 500;
    transition: all 0.2s;
  }}
  .archive-nav a:hover {{
    background: #fff;
    border-color: #667eea;
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

  <div class="trend">{trend_summary}</div>

  <div class="archive-nav">
    <a href="index.html">📚 历史简报</a>
  </div>

  {sections_html}

  <div class="footer">
    <p>Powered by Claude · 自动生成</p>
  </div>
</div>
</body>
</html>"""


def get_favicon_url(source_url):
    try:
        from urllib.parse import urlparse
        parsed = urlparse(source_url)
        if parsed.hostname:
            return f"https://www.google.com/s2/favicons?domain={parsed.hostname}&sz=32"
    except Exception:
        pass
    return ""


def is_valid_link(url):
    """检查是否是有效的具体链接（不是域名首页）"""
    if not url:
        return False
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return bool(parsed.scheme and parsed.hostname and parsed.path and parsed.path != "/")


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

                has_link = is_valid_link(source_url)
                favicon = get_favicon_url(source_url) if has_link else ""
                favicon_img = f'<img src="{html_module.escape(favicon)}" alt="" onerror="this.style.display=\'none\'">' if favicon else ""
                author_span = f'<span class="card-author">{author}</span>' if author else ""

                if has_link:
                    card_open = f'<a class="card" href="{html_module.escape(source_url)}" target="_blank" rel="noopener">'
                    card_close = '</a>'
                    link_icon = '<span class="card-link-icon">↗</span>'
                else:
                    card_open = '<div class="card no-link">'
                    card_close = '</div>'
                    link_icon = ''

                cards_html += f"""{card_open}
  <div class="card-headline">{headline}</div>
  <div class="card-summary">{summary}</div>
  <div class="card-meta">
    <span class="card-source">{favicon_img}{source_name}</span>
    {author_span}
    {link_icon}
  </div>
{card_close}
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

    return HTML_TEMPLATE.format(date=date, trend_summary=trend, sections_html=sections_html)


INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 简报 · 归档</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif; background:#f5f5f7; color:#1d1d1f; min-height:100vh; }}
  .container {{ max-width:600px; margin:0 auto; padding:40px 16px; }}
  h1 {{ text-align:center; font-size:28px; font-weight:700; margin-bottom:6px; }}
  .subtitle {{ text-align:center; color:#86868b; font-size:13px; margin-bottom:28px; }}
  .list a {{
    display:flex; justify-content:space-between; align-items:center;
    padding:15px 18px; margin-bottom:8px;
    background:#fff; border-radius:12px; box-shadow:0 1px 3px rgba(0,0,0,0.06);
    color:#1d1d1f; text-decoration:none; font-size:15px; font-weight:500;
    transition: all 0.2s;
  }}
  .list a:hover {{ box-shadow:0 4px 12px rgba(0,0,0,0.1); transform:translateX(4px); }}
  .list a span {{ color:#86868b; font-size:18px; }}
</style>
</head>
<body>
<div class="container">
  <h1>📡 AI 简报</h1>
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
    print(f"   HTML: {filepath}")

    html_files = sorted(
        [f for f in os.listdir(DOCS_DIR) if f.endswith(".html") and f != "index.html"],
        reverse=True
    )
    links = ""
    for fname in html_files:
        d = fname.replace(".html", "")
        links += f'    <a href="{fname}">AI 简报 · {d} <span>→</span></a>\n'

    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(INDEX_TEMPLATE.format(links=links))

    return f"{PAGES_BASE_URL}/{date}.html"


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
    print(f"   {len(builders_data['builders'])} builders")

    print("   搜索 + 生成...")
    briefing_data = search_and_get_json(builders_data)
    print(f"   {len(briefing_data.get('sections', []))} sections")

    print("   渲染 HTML...")
    html_content = render_html(briefing_data)
    page_url = save_html(briefing_data, html_content)
    print(f"   URL: {page_url}")

    today = briefing_data.get("date", datetime.date.today().strftime("%Y-%m-%d"))
    send_bark("📡 AI 简报已更新", f"AI 简报 · {today}", url=page_url)
    print("✅ 完成")


if __name__ == "__main__":
    main()
