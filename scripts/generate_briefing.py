#!/usr/bin/env python3
"""每日 AI 简报 — 中文深度摘要，信息终点而非链接导航"""

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
        print(f"   [API #{round_count}]")
        result = call_claude(messages, tools=tools)
        stop_reason = result.get("stop_reason", "")
        content_blocks = result.get("content", [])
        print(f"   [stop: {stop_reason}, blocks: {len(content_blocks)}]")
        if stop_reason == "end_turn":
            return "\n".join(b["text"] for b in content_blocks if b.get("type") == "text")
        messages.append({"role": "assistant", "content": content_blocks})
        tool_results = [{"type": "tool_result", "tool_use_id": b["id"], "content": "done"}
                        for b in content_blocks if b.get("type") == "tool_use"]
        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        else:
            return "\n".join(b["text"] for b in content_blocks if b.get("type") == "text")


def search_and_get_json(builders_data):
    today = datetime.date.today().strftime("%Y-%m-%d")
    builder_names = ", ".join(f'{b["name"]} ({b["role"]})' for b in builders_data["builders"])
    podcast_names = ", ".join(p["name"] for p in builders_data["podcasts"])

    # Step 1: 搜索原始信息
    search_prompt = f"""今天是 {today}。搜索以下 AI 领域关键人物和机构的最新动态（最近一周内都可以）：

人物：{builder_names}
播客：{podcast_names}
博客：Anthropic、OpenAI、Google DeepMind

对每条信息，尽量详细记录：
- 谁发布/说了什么
- 具体的技术细节、观点论据、产品特性
- 背景和上下文

用中文记录，越详细越好。"""

    print("   Step 1: 搜索...")
    raw_info = call_claude_with_search(search_prompt)
    print(f"   原始: {len(raw_info)} chars")

    # Step 2: 生成深度摘要 JSON
    format_prompt = f"""你是一个中文 AI 行业简报作者。基于以下原始信息，生成一份深度简报。

原始信息：
---
{raw_info}
---

要求：
1. 每条内容写成 200-400 字的完整中文短文，不是一两句话
2. 包含：谁（人名+身份）、说了/做了什么（核心内容完整展开）、为什么重要
3. 读者是中文用户，看不懂英文，不会点链接看原文。你的摘要就是他获取信息的唯一渠道
4. 语言要有信息密度，不要水字数，但也不要过度压缩丢失关键细节

直接输出 JSON（不要 ```）：

{{
  "date": "{today}",
  "trend_summary": "今日趋势一句话（中文，15-25字）",
  "articles": [
    {{
      "tag": "分类标签（如：模型发布/行业观点/产品更新/融资动态/技术博客/播客精华）",
      "author": "人名",
      "author_title": "身份（如 OpenAI CEO / Anthropic 研究员）",
      "title": "这条信息的中文标题（10-20字）",
      "body": "200-400字的完整中文摘要。分段用 \\n\\n 分隔。"
    }}
  ]
}}

规则：
- articles 按重要性排序，最重要的在前
- 同一个人的多条动态可以合并为一篇
- 没有实质内容的不要凑数
- body 里不要出现英文原文，全部翻译为中文"""

    print("   Step 2: 深度摘要...")
    raw_json = call_claude([{"role": "user", "content": format_prompt}])
    text = "\n".join(b["text"] for b in raw_json.get("content", []) if b.get("type") == "text").strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    print(f"   JSON: {len(text)} chars")

    # 解析 + 自动修复
    for attempt in range(3):
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            if attempt < 2:
                print(f"   [JSON fix attempt {attempt+1}: {e}]")
                fix = call_claude([{"role": "user", "content": f"修复这段 JSON 的语法错误，只输出正确 JSON（不要 ```）：\n\n{text}"}])
                text = "\n".join(b["text"] for b in fix.get("content", []) if b.get("type") == "text").strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            else:
                print(f"   [JSON failed]")
                return {
                    "date": today,
                    "trend_summary": "AI 行业每日动态",
                    "articles": [{"tag": "简报", "author": "", "author_title": "",
                                  "title": "今日简报", "body": raw_info[:3000]}]
                }


# ──────────── HTML ────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 简报 · {date}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif;
    background: #fafafa;
    color: #1a1a1a;
    line-height: 1.85;
    -webkit-font-smoothing: antialiased;
  }}
  .container {{ max-width: 680px; margin: 0 auto; padding: 20px 18px 60px; }}

  .header {{
    text-align: center;
    padding: 32px 0 24px;
    margin-bottom: 20px;
  }}
  .header-sub {{ font-size: 11px; letter-spacing: 2px; color: #999; text-transform: uppercase; margin-bottom: 8px; }}
  .header h1 {{ font-size: 26px; font-weight: 700; color: #1a1a1a; }}
  .header .date {{ font-size: 14px; color: #999; margin-top: 4px; }}

  .trend {{
    background: #f0f0f5;
    border-left: 4px solid #5b5ea6;
    border-radius: 0 10px 10px 0;
    padding: 16px 20px;
    margin-bottom: 28px;
    font-size: 16px;
    color: #333;
    font-weight: 500;
  }}

  .nav {{ text-align: center; margin-bottom: 24px; }}
  .nav a {{
    font-size: 13px; color: #5b5ea6; text-decoration: none;
    padding: 5px 14px; border: 1px solid #e0e0e0; border-radius: 6px;
  }}

  .article {{
    background: #fff;
    border-radius: 12px;
    padding: 22px 22px 18px;
    margin-bottom: 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  }}
  .article-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
    flex-wrap: wrap;
  }}
  .tag {{
    font-size: 11px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 4px;
    color: #fff;
    white-space: nowrap;
  }}
  .tag-模型发布 {{ background: #e74c3c; }}
  .tag-行业观点 {{ background: #3498db; }}
  .tag-产品更新 {{ background: #2ecc71; }}
  .tag-融资动态 {{ background: #f39c12; }}
  .tag-技术博客 {{ background: #9b59b6; }}
  .tag-播客精华 {{ background: #1abc9c; }}
  .tag-default {{ background: #7f8c8d; }}

  .author-info {{
    font-size: 13px;
    color: #666;
  }}
  .author-name {{
    font-weight: 600;
    color: #1a1a1a;
  }}

  .article-title {{
    font-size: 18px;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 10px;
    line-height: 1.5;
  }}
  .article-body {{
    font-size: 15px;
    color: #333;
    line-height: 1.9;
  }}
  .article-body p {{
    margin-bottom: 10px;
  }}
  .article-body p:last-child {{
    margin-bottom: 0;
  }}

  .footer {{
    text-align: center;
    padding-top: 24px;
    font-size: 12px;
    color: #aaa;
  }}

  @media (max-width: 480px) {{
    .container {{ padding: 14px 14px 40px; }}
    .article {{ padding: 18px 16px 14px; }}
    .article-title {{ font-size: 17px; }}
    .article-body {{ font-size: 14.5px; }}
  }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="header-sub">Follow Builders, Not Influencers</div>
    <h1>AI 简报</h1>
    <div class="date">{date}</div>
  </div>

  <div class="trend">💡 {trend_summary}</div>

  <div class="nav"><a href="index.html">📚 历史简报</a></div>

  {articles_html}

  <div class="footer">自动生成 · Powered by Claude</div>
</div>
</body>
</html>"""


TAG_CLASSES = {"模型发布", "行业观点", "产品更新", "融资动态", "技术博客", "播客精华"}


def render_html(data):
    date = html_module.escape(data.get("date", ""))
    trend = html_module.escape(data.get("trend_summary", ""))

    articles_html = ""
    for a in data.get("articles", []):
        tag = a.get("tag", "")
        tag_class = f"tag-{tag}" if tag in TAG_CLASSES else "tag-default"
        author = html_module.escape(a.get("author", ""))
        author_title = html_module.escape(a.get("author_title", ""))
        title = html_module.escape(a.get("title", ""))

        # body: 按 \n\n 分段
        body_raw = a.get("body", "")
        paragraphs = [p.strip() for p in body_raw.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [p.strip() for p in body_raw.split("\n") if p.strip()]
        body_html = "".join(f"<p>{html_module.escape(p)}</p>" for p in paragraphs)

        author_line = ""
        if author:
            author_line = f'<span class="author-name">{author}</span>'
            if author_title:
                author_line += f" · {author_title}"
            author_line = f'<div class="author-info">{author_line}</div>'

        articles_html += f"""<div class="article">
  <div class="article-header">
    <span class="tag {html_module.escape(tag_class)}">{html_module.escape(tag)}</span>
    {author_line}
  </div>
  <div class="article-title">{title}</div>
  <div class="article-body">{body_html}</div>
</div>
"""

    return HTML_TEMPLATE.format(date=date, trend_summary=trend, articles_html=articles_html)


INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 简报</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; background:#fafafa; color:#1a1a1a; }}
  .container {{ max-width:600px; margin:0 auto; padding:40px 16px; }}
  h1 {{ text-align:center; font-size:24px; margin-bottom:6px; }}
  .sub {{ text-align:center; color:#999; font-size:12px; margin-bottom:28px; }}
  .list a {{
    display:flex; justify-content:space-between; align-items:center;
    padding:14px 18px; margin-bottom:8px;
    background:#fff; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.04);
    color:#1a1a1a; text-decoration:none; font-size:15px;
  }}
  .list a:active {{ background:#f5f5f5; }}
  .list a span {{ color:#ccc; }}
</style>
</head>
<body>
<div class="container">
  <h1>AI 简报</h1>
  <div class="sub">Follow Builders, Not Influencers</div>
  <div class="list">{links}</div>
</div>
</body>
</html>"""


def save_html(data, html_content):
    os.makedirs(DOCS_DIR, exist_ok=True)
    date = data["date"]
    with open(os.path.join(DOCS_DIR, f"{date}.html"), "w", encoding="utf-8") as f:
        f.write(html_content)

    html_files = sorted(
        [f for f in os.listdir(DOCS_DIR) if f.endswith(".html") and f != "index.html"],
        reverse=True
    )
    links = "".join(f'<a href="{fn}">{fn.replace(".html","")} <span>→</span></a>\n' for fn in html_files)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(INDEX_TEMPLATE.format(links=links))

    return f"{PAGES_BASE_URL}/{date}.html"


def send_bark(title, body, url=None):
    payload = {"title": title, "body": body, "level": "timeSensitive"}
    if url:
        payload["url"] = url
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BARK_URL.rstrip("/"), data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    print("📡 AI 简报...")
    builders_data = load_builders()
    briefing = search_and_get_json(builders_data)
    n = len(briefing.get("articles", []))
    print(f"   {n} articles")

    html = render_html(briefing)
    url = save_html(briefing, html)
    print(f"   {url}")

    today = briefing.get("date", datetime.date.today().strftime("%Y-%m-%d"))
    send_bark("📡 AI 简报已更新", f"{today} · {n} 条深度摘要", url=url)
    print("✅ done")


if __name__ == "__main__":
    main()
