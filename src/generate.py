from __future__ import annotations

import datetime as dt
import json
import os
import re
import textwrap
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "generated" / "current"
RUN = ROOT / ".run"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
STATE_PATH = ROOT / "data" / "state.json"

W, H = 1080, 1350
COLORS = CONFIG["colors"]
BG = COLORS["background"]
INK = COLORS["ink"]
MUTED = COLORS["muted"]
LIME = COLORS["lime"]
GREEN = COLORS["green"]
BLUE = COLORS["blue"]
WHITE = COLORS["white"]
LINE = COLORS["line"]


def load_local_env() -> None:
    path = ROOT / ".env.local"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def choose_font(bold: bool = False) -> str:
    candidates = [
        "C:/Windows/Fonts/NotoSansKR-Bold.ttf" if bold else "C:/Windows/Fonts/NotoSansKR-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("Noto Sans KR/CJK font was not found")


FONT_REG = choose_font(False)
FONT_BOLD = choose_font(True)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)


def response_text(payload: dict) -> str:
    parts: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def parse_json_text(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def pillar_for_today() -> str:
    weekday = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).weekday()
    return {
        0: CONFIG["pillars"]["monday"],
        2: CONFIG["pillars"]["wednesday"],
        4: CONFIG["pillars"]["friday"],
    }.get(weekday, "저장해두고 바로 쓰는 AI 활용법")


def create_content() -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing")

    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    recent = [item.get("topic", "") for item in state.get("published", [])[-20:]]
    schema_example = {
        "topic": "한 문장 주제",
        "hook": "표지용 22자 이내 제목",
        "caption": "인스타그램 본문. 핵심 요약과 저장 CTA 포함",
        "hashtags": ["AI써봄", "AI활용법"],
        "cards": [
            {
                "eyebrow": "짧은 영문 또는 한글 섹션명",
                "title": "28자 이내 제목",
                "subtitle": "55자 이내 설명",
                "bullets": ["18자 안팎 핵심 1", "핵심 2", "핵심 3"],
                "callout": "복사하거나 기억할 한 줄",
            }
        ],
    }
    prompt = f"""
너는 한국 인스타그램 계정 'AI 써봄(@ai.sseobom)'의 편집장이다.
오늘의 콘텐츠 기둥은 '{pillar_for_today()}'이다.
최신 AI 흐름을 웹에서 한 번 확인하고, AI 초보 직장인이 오늘 바로 써볼 수 있는 카드뉴스 주제 하나를 고른다.

편집 원칙:
- 과장된 생산성 약속을 쓰지 않는다.
- 실제 행동, 전후 비교, 복사 가능한 프롬프트나 체크리스트를 우선한다.
- 사실과 추정을 구분하고 유료/무료, 제한 조건이 중요하면 명시한다.
- 최근 게시 주제와 겹치지 않는다: {json.dumps(recent, ensure_ascii=False)}
- 카드 7장 고정. 1장은 강한 문제 제기, 2~6장은 설명/비교/절차, 7장은 저장용 요약과 CTA.
- 각 카드 bullets는 2~3개. 문장은 짧고 자연스러운 한국어로 쓴다.
- 해시태그는 8~12개이며 # 기호 없이 배열에 넣는다.
- 캡션에는 URL, 마크다운 링크, 괄호형 출처 표기를 넣지 않는다. 필요한 경우 출처 서비스 이름만 자연어로 언급한다.
- 광고처럼 보이는 문구, 출처 없는 정확한 수치, 확인하지 않은 최신 기능 단정은 금지한다.

아래 구조와 정확히 같은 JSON 객체만 출력한다. 마크다운은 쓰지 않는다.
{json.dumps(schema_example, ensure_ascii=False)}
""".strip()

    body = {
        "model": CONFIG["model"],
        "input": prompt,
        "tools": [{"type": "web_search"}],
        "max_output_tokens": CONFIG["max_output_tokens"],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        safe_body = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"OpenAI API error {exc.code}: {safe_body}") from exc

    result = parse_json_text(response_text(payload))
    cards = result.get("cards")
    if not isinstance(cards, list) or len(cards) != CONFIG["cards_per_post"]:
        raise RuntimeError("The generated content did not contain exactly 7 cards")
    return result


def wrap_by_width(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        current = ""
        for ch in paragraph:
            candidate = current + ch
            if not current or draw.textbbox((0, 0), candidate, font=fnt)[2] <= width:
                current = candidate
            else:
                lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines


def draw_wrapped(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, fnt: ImageFont.FreeTypeFont,
                 fill: str, width: int, gap: int = 12, max_lines: int | None = None) -> int:
    lines = wrap_by_width(draw, text, fnt, width)
    if max_lines:
        lines = lines[:max_lines]
    for line in lines:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += fnt.size + gap
    return y


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int = 28,
            fill: str = WHITE, outline: str | None = None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def render_cover(card: dict, index: int) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    rounded(draw, (64, 62, 300, 114), radius=26, fill=LIME)
    draw.text((88, 74), "SAVEABLE AI", font=font(20, True), fill=INK)
    draw.text((64, 171), CONFIG["brand_name"], font=font(30, True), fill=GREEN)
    y = draw_wrapped(draw, 64, 245, card["title"], font(82, True), INK, 930, 15, 4)
    y = draw_wrapped(draw, 69, y + 35, card.get("subtitle", ""), font(29), MUTED, 830, 14, 3)

    accent = BLUE if index % 2 else GREEN
    draw.ellipse((670, 700, 1140, 1170), fill=accent)
    draw.ellipse((770, 800, 1040, 1070), fill=LIME)
    draw.rectangle((64, 770, 650, 1080), fill=INK)
    callout = card.get("callout") or "넘겨서 핵심만 확인하세요"
    draw_wrapped(draw, 102, 824, callout, font(35, True), WHITE, 510, 16, 4)
    rounded(draw, (64, 1195, 390, 1262), radius=32, fill=INK)
    draw.text((93, 1211), "1분 AI 활용법", font=font(22, True), fill=WHITE)
    draw.text((850, 1214), "넘겨보기", font=font(20, True), fill=INK)
    draw.polygon([(1008, 1228), (985, 1213), (985, 1243)], fill=GREEN)
    return img


def render_detail(card: dict, index: int) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.text((64, 54), CONFIG["series_name"], font=font(25, True), fill=INK)
    draw.text((64, 92), card.get("eyebrow", "AI NOTE"), font=font(18), fill=MUTED)
    page = f"{index:02d} / 07"
    pw = draw.textbbox((0, 0), page, font=font(18, True))[2]
    draw.text((W - 64 - pw, 69), page, font=font(18, True), fill=GREEN)
    draw.line((64, 132, W - 64, 132), fill=LINE, width=2)

    accent = LIME if index % 2 else BLUE
    rounded(draw, (64, 184, 164, 284), radius=28, fill=accent)
    label_color = INK if accent == LIME else WHITE
    draw.text((92, 205), f"{index:02d}", font=font(40, True), fill=label_color)
    y = draw_wrapped(draw, 196, 176, card["title"], font(58, True), INK, 800, 14, 2)
    y = draw_wrapped(draw, 199, y + 15, card.get("subtitle", ""), font(26), MUTED, 780, 12, 3)

    bullets = card.get("bullets", [])[:3]
    box_y = max(410, y + 35)
    for pos, bullet in enumerate(bullets):
        height = 150
        rounded(draw, (64, box_y, 1016, box_y + height), radius=28, fill=WHITE, outline=LINE, width=2)
        rounded(draw, (92, box_y + 39, 152, box_y + 99), radius=22, fill=accent)
        number_color = INK if accent == LIME else WHITE
        draw.text((110, box_y + 48), str(pos + 1), font=font(23, True), fill=number_color)
        draw_wrapped(draw, 184, box_y + 39, str(bullet), font(29, True), INK, 770, 10, 2)
        box_y += height + 22

    callout_y = min(max(box_y + 20, 940), 1095)
    rounded(draw, (64, callout_y, 1016, 1200), radius=32, fill=INK)
    draw.text((94, callout_y + 28), "SAVE THIS", font=font(18, True), fill=accent)
    draw_wrapped(draw, 94, callout_y + 70, card.get("callout", "저장하고 바로 써보세요"),
                 font(27, True), WHITE, 850, 12, 3)

    draw.line((64, H - 88, W - 64, H - 88), fill=LINE, width=2)
    draw.text((64, H - 62), "직접 써보고 비교한 AI 활용법", font=font(17), fill=MUTED)
    draw.ellipse((W - 91, H - 62, W - 65, H - 36), fill=LIME)
    return img


def render_cards(content: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.jpg"):
        old.unlink()
    for idx, card in enumerate(content["cards"], start=1):
        img = render_cover(card, idx) if idx == 1 else render_detail(card, idx)
        img.save(OUT / f"{idx:02d}.jpg", quality=94, subsampling=0, optimize=True)


def main() -> None:
    load_local_env()
    content = create_content()
    hashtags = " ".join(f"#{str(tag).lstrip('#')}" for tag in content.get("hashtags", []))
    caption = str(content.get("caption", "")).strip()
    caption = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", caption)
    caption = re.sub(r"https?://\S+", "", caption)
    caption = re.sub(r"[ \t]{2,}", " ", caption).strip()
    content["caption"] = caption
    content["caption_full"] = f"{caption}\n\n{hashtags}".strip()
    content["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    content["is_ai_generated"] = True
    render_cards(content)
    (OUT / "post.json").write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    RUN.mkdir(exist_ok=True)
    (RUN / "post_json_path.txt").write_text("generated/current/post.json", encoding="utf-8")
    print(f"Generated {len(content['cards'])} cards for: {content['topic']}")


if __name__ == "__main__":
    main()
