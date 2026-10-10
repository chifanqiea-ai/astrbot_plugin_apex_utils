"""生成效果预览图：模拟机器人在聊天中发出的「段位图标 + 战绩文本」消息。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PIL import Image, ImageDraw, ImageFont

import apex_api
import apex_constants as C
import dev_selftest as T

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render(out_path: Path) -> Path:
    data = apex_api.parse_player_payload(T.SAMPLE)
    text = apex_api.format_player_text(
        data,
        platform="PC",
        max_trackers=8,
        preferred_trackers=C.PREFERRED_TRACKERS,
        ignored_trackers=C.IGNORED_TRACKERS,
    )

    body_font = load_font(21)
    small_font = load_font(16)
    lines = text.splitlines()

    padding = 28
    line_height = 30
    width = 620
    height = padding * 2 + 200 + line_height * len(lines)
    image = Image.new("RGB", (width, height), (245, 246, 250))
    draw = ImageDraw.Draw(image)

    # 聊天气泡
    bubble = (16, 16, width - 16, height - 16)
    draw.rounded_rectangle(bubble, radius=18, fill=(255, 255, 255), outline=(219, 222, 229), width=2)
    # 头像占位
    draw.ellipse((32, 34, 96, 98), fill=(88, 101, 242))
    draw.text((64, 66), "BOT", font=small_font, fill=(255, 255, 255), anchor="mm")
    draw.text((112, 40), "Apex 战绩查询", font=load_font(18), fill=(60, 64, 78))

    # 段位图标占位（真实使用时会由数据源下发 PNG）
    badge_box = (112, 70, 112 + 210, 70 + 130)
    draw.rounded_rectangle(badge_box, radius=12, fill=(38, 42, 58), outline=(120, 128, 158), width=2)
    draw.text(
        ((badge_box[0] + badge_box[2]) // 2, 118),
        "DIAMOND II",
        font=load_font(30),
        fill=(150, 208, 255),
        anchor="mm",
    )
    draw.text(
        ((badge_box[0] + badge_box[2]) // 2, 162),
        "rankImg（段位徽章图片）",
        font=small_font,
        fill=(180, 186, 205),
        anchor="mm",
    )

    y = 220
    for line in lines:
        color = (33, 37, 41)
        font = body_font
        if line.startswith("【"):
            font, color = load_font(23), (88, 101, 242)
        elif line.startswith("──"):
            color = (130, 136, 152)
        elif line.startswith("━"):
            color = (205, 210, 220)
            draw.text((padding + 20, y), "─" * 34, font=body_font, fill=color)
            y += 22
            continue
        elif line.startswith("数据来源"):
            font, color = small_font, (150, 155, 170)
        draw.text((padding + 20, y), line, font=font, fill=color)
        y += line_height

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    return out_path


if __name__ == "__main__":
    target = render(HERE / "docs" / "preview.png")
    print(f"预览图已生成：{target}")
