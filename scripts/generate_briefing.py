#!/usr/bin/env python3
"""每日 AI 简报 — 故事卷轴 + 对话体"""

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

    # Step 1: 搜索
    search_prompt = f"""今天是 {today}。搜索以下 AI 领域关键人物和机构的最新动态（最近一周内）：

人物：{builder_names}
播客：{podcast_names}
博客：Anthropic、OpenAI、Google DeepMind

对每条信息尽量详细记录：谁、说了/做了什么、技术细节、背景。中文记录。"""

    print("   Step 1: 搜索...")
    raw_info = call_claude_with_search(search_prompt)
    print(f"   原始: {len(raw_info)} chars")

    # Step 2: 生成故事卷轴 JSON
    format_prompt = f"""你是一个给外行朋友讲 AI 新闻的人。基于以下原始信息，生成一份「故事卷轴」简报。

原始信息：
---
{raw_info}
---

要求：
1. 用对话口语写，像在跟一个完全不懂 AI 的朋友聊天
2. 精选 3-5 条最值得讲的内容（不要贪多）
3. 内容之间要有逻辑连接和过渡（不是独立的几块）
4. 提到的人物/公司/术语，第一次出现时自然地解释（融入对话，不要单独列）
5. 如果有某个术语特别重要且解释起来需要篇幅，单独做一个术语卡片屏
6. 最后一屏做一个收尾总结

直接输出 JSON（不要 ```）：

{{
  "date": "{today}",
  "screens": [
    {{
      "type": "intro",
      "text": "开场白，点出今天的主线是什么，1-3句话，口语化"
    }},
    {{
      "type": "story",
      "label": "短标签如'模型发布'或'行业观点'",
      "text": "200-350字的对话体叙述。像跟朋友聊天一样讲清楚这件事。第一次提到的人要介绍身份。段落间用 \\n\\n 分隔。"
    }},
    {{
      "type": "story",
      "label": "标签",
      "text": "下一个信息点。开头要有过渡句，跟上一屏有呼应。"
    }},
    {{
      "type": "term",
      "word": "术语名",
      "explain": "用大白话解释这个术语，可以用比喻，3-5句话"
    }},
    {{
      "type": "outro",
      "text": "收尾总结，今天的核心收获是什么，1-3句话"
    }}
  ]
}}

规则：
- screens 数量 6-9 个（1 intro + 3-5 story + 0-2 term + 1 outro）
- 全部中文，不要出现英文
- 对话感要强，可以用"你知道吗""说白了""有意思的是"这类口语
- 不要用"大家好""今天的简报"这种播报腔
- term 类型的屏只在术语确实需要额外解释时才加，不要每期都硬加"""

    print("   Step 2: 故事卷轴...")
    raw_json = call_claude([{"role": "user", "content": format_prompt}])
    text = "\n".join(b["text"] for b in raw_json.get("content", []) if b.get("type") == "text").strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    print(f"   JSON: {len(text)} chars")

    for attempt in range(3):
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            if attempt < 2:
                print(f"   [fix attempt {attempt+1}: {e}]")
                fix = call_claude([{"role": "user", "content": f"修复 JSON 语法错误，只输出正确 JSON（不要 ```）：\n\n{text}"}])
                text = "\n".join(b["text"] for b in fix.get("content", []) if b.get("type") == "text").strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            else:
                print("   [JSON failed]")
                return {"date": today, "screens": [
                    {"type": "intro", "text": "今天的简报生成遇到了点问题，明天见。"}
                ]}


# ──────── HTML ────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>AI 简报 · {date}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html {{ scroll-snap-type: y mandatory; scroll-behavior: smooth; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
    background: #fafafa;
    color: #1a1a1a;
    -webkit-font-smoothing: antialiased;
    overflow-x: hidden;
  }}

  .screen {{
    min-height: 100vh;
    min-height: 100dvh;
    scroll-snap-align: start;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 40px 24px;
    position: relative;
  }}
  .screen-inner {{
    max-width: 560px;
    margin: 0 auto;
    width: 100%;
  }}

  /* Intro */
  .screen-intro {{
    background: #fafafa;
  }}
  .intro-date {{
    font-size: 12px;
    letter-spacing: 2px;
    color: #aaa;
    text-transform: uppercase;
    margin-bottom: 16px;
  }}
  .intro-text {{
    font-size: 22px;
    font-weight: 600;
    line-height: 1.7;
    color: #1a1a1a;
  }}
  .intro-hint {{
    position: absolute;
    bottom: 32px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 13px;
    color: #ccc;
    animation: bounce 2s ease infinite;
  }}
  @keyframes bounce {{
    0%, 100% {{ transform: translateX(-50%) translateY(0); }}
    50% {{ transform: translateX(-50%) translateY(-8px); }}
  }}

  /* Story */
  .screen-story {{
    background: #fff;
    border-bottom: 1px solid #f0f0f0;
  }}
  .story-label {{
    display: inline-block;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 12px;
    border-radius: 4px;
    margin-bottom: 18px;
    color: #fff;
  }}
  .label-模型发布 {{ background: #e74c3c; }}
  .label-行业观点 {{ background: #3498db; }}
  .label-产品更新 {{ background: #2ecc71; }}
  .label-融资动态 {{ background: #f39c12; }}
  .label-技术博客 {{ background: #9b59b6; }}
  .label-播客精华 {{ background: #1abc9c; }}
  .label-重要动态 {{ background: #e67e22; }}
  .label-default {{ background: #7f8c8d; }}

  .story-text {{
    font-size: 17px;
    line-height: 2;
    color: #2a2a2a;
  }}
  .story-text p {{
    margin-bottom: 14px;
  }}
  .story-text p:last-child {{
    margin-bottom: 0;
  }}

  /* Term */
  .screen-term {{
    background: #f0f0f5;
  }}
  .term-badge {{
    font-size: 12px;
    color: #5b5ea6;
    font-weight: 600;
    letter-spacing: 1px;
    margin-bottom: 12px;
  }}
  .term-word {{
    font-size: 26px;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 16px;
  }}
  .term-explain {{
    font-size: 17px;
    line-height: 2;
    color: #444;
  }}

  /* Outro */
  .screen-outro {{
    background: #fafafa;
  }}
  .outro-text {{
    font-size: 20px;
    font-weight: 600;
    line-height: 1.8;
    color: #1a1a1a;
  }}
  .outro-bye {{
    margin-top: 20px;
    font-size: 14px;
    color: #aaa;
  }}
  .outro-nav {{
    margin-top: 28px;
  }}
  .outro-nav a {{
    font-size: 13px;
    color: #5b5ea6;
    text-decoration: none;
    padding: 8px 18px;
    border: 1px solid #ddd;
    border-radius: 8px;
  }}

  /* Progress dots */
  .progress {{
    position: fixed;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    flex-direction: column;
    gap: 8px;
    z-index: 100;
  }}
  .dot {{
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #ddd;
    transition: all 0.3s;
  }}
  .dot.active {{
    background: #5b5ea6;
    transform: scale(1.5);
  }}

  @media (max-width: 480px) {{
    .screen {{ padding: 32px 20px; }}
    .intro-text {{ font-size: 20px; }}
    .story-text {{ font-size: 16px; line-height: 1.95; }}
    .term-word {{ font-size: 22px; }}
    .outro-text {{ font-size: 18px; }}
  }}
</style>
</head>
<body>

<div class="progress" id="progress">
  {dots_html}
</div>

{screens_html}

<script>
  const screens = document.querySelectorAll('.screen');
  const dots = document.querySelectorAll('.dot');
  const observer = new IntersectionObserver((entries) => {{
    entries.forEach(entry => {{
      if (entry.isIntersecting) {{
        const idx = [...screens].indexOf(entry.target);
        dots.forEach((d, i) => d.classList.toggle('active', i === idx));
      }}
    }});
  }}, {{ threshold: 0.5 }});
  screens.forEach(s => observer.observe(s));
</script>

</body>
</html>"""


LABEL_CLASSES = {"模型发布", "行业观点", "产品更新", "融资动态", "技术博客", "播客精华", "重要动态"}


def render_html(data):
    date = html_module.escape(data.get("date", ""))
    screens = data.get("screens", [])

    dots_html = "\n  ".join(f'<div class="dot{"  active" if i == 0 else ""}"></div>' for i in range(len(screens)))

    screens_html = ""
    for screen in screens:
        stype = screen.get("type", "story")
        inner = ""

        if stype == "intro":
            text = html_module.escape(screen.get("text", ""))
            inner = f"""<div class="screen screen-intro">
  <div class="screen-inner">
    <div class="intro-date">AI 简报 · {date}</div>
    <div class="intro-text">{text}</div>
  </div>
  <div class="intro-hint">↓ 向下滑动</div>
</div>"""

        elif stype == "story":
            label = screen.get("label", "")
            label_class = f"label-{label}" if label in LABEL_CLASSES else "label-default"
            raw_text = screen.get("text", "")
            paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
            if not paragraphs:
                paragraphs = [p.strip() for p in raw_text.split("\n") if p.strip()]
            body = "".join(f"<p>{html_module.escape(p)}</p>" for p in paragraphs)
            inner = f"""<div class="screen screen-story">
  <div class="screen-inner">
    <div class="story-label {html_module.escape(label_class)}">{html_module.escape(label)}</div>
    <div class="story-text">{body}</div>
  </div>
</div>"""

        elif stype == "term":
            word = html_module.escape(screen.get("word", ""))
            explain = html_module.escape(screen.get("explain", ""))
            inner = f"""<div class="screen screen-term">
  <div class="screen-inner">
    <div class="term-badge">💡 术语卡片</div>
    <div class="term-word">{word}</div>
    <div class="term-explain">{explain}</div>
  </div>
</div>"""

        elif stype == "outro":
            text = html_module.escape(screen.get("text", ""))
            inner = f"""<div class="screen screen-outro">
  <div class="screen-inner">
    <div class="outro-text">{text}</div>
    <div class="outro-bye">明天见 👋</div>
    <div class="outro-nav"><a href="index.html">📚 历史简报</a></div>
  </div>
</div>"""

        screens_html += inner + "\n"

    return HTML_TEMPLATE.format(date=date, dots_html=dots_html, screens_html=screens_html)


INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 简报</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; background:#fafafa; color:#1a1a1a; }}
  .c {{ max-width:560px; margin:0 auto; padding:48px 20px; }}
  h1 {{ font-size:22px; text-align:center; margin-bottom:4px; }}
  .sub {{ text-align:center; color:#aaa; font-size:12px; margin-bottom:32px; }}
  a {{
    display:flex; justify-content:space-between;
    padding:16px 18px; margin-bottom:8px;
    background:#fff; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.04);
    color:#1a1a1a; text-decoration:none; font-size:15px;
  }}
  a:active {{ background:#f5f5f5; }}
  a span {{ color:#ccc; }}
</style>
</head>
<body>
<div class="c">
  <h1>AI 简报</h1>
  <div class="sub">Follow Builders, Not Influencers</div>
  {links}
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
    n = len(briefing.get("screens", []))
    print(f"   {n} screens")

    html = render_html(briefing)
    url = save_html(briefing, html)
    print(f"   {url}")

    today = briefing.get("date", datetime.date.today().strftime("%Y-%m-%d"))
    send_bark("📡 AI 简报已更新", f"{today}", url=url)
    print("✅ done")


if __name__ == "__main__":
    main()
