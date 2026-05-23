import os
from PIL import Image, ImageDraw, ImageFont


class CyberImageRenderer:
    def __init__(self, bg_path: str, font_path: str = None):
        self.bg_path = bg_path
        self.font_path = font_path if font_path and os.path.exists(font_path) else None

    def _get_font(self, size: int):
        if self.font_path:
            return ImageFont.truetype(self.font_path, size)
        return ImageFont.load_default()

    def _wrap_text(self, text: str, font, max_width: int) -> list:
        lines = []
        current_line = ""
        for char in text:
            test_line = current_line + char
            bbox = font.getbbox(test_line)
            line_width = bbox[2] - bbox[0]
            if line_width > max_width and current_line:
                lines.append(current_line)
                current_line = char
            else:
                current_line = test_line
        if current_line:
            lines.append(current_line)
        return lines

    def render(self, data: dict, output_path: str):
        base_img = Image.open(self.bg_path).convert("RGBA")
        base_w, base_h = base_img.size

        top_h, bottom_h = 250, 250
        margin_x = 75
        content_w = base_w - (margin_x * 2)

        top_slice = base_img.crop((0, 0, base_w, top_h))
        bottom_slice = base_img.crop((0, base_h - bottom_h, base_w, base_h))

        font_title = self._get_font(32)
        font_sub = self._get_font(22)
        font_body = self._get_font(18)

        layout_elements = []

        def add_text(text: str, font, fill: str, spacing: int = 6):
            for line in self._wrap_text(text, font, content_w):
                bbox = font.getbbox(line)
                line_h = bbox[3] - bbox[1]
                layout_elements.append(("text", line, font, fill, line_h + spacing))

        def add_space(height: int):
            layout_elements.append(("space", "", None, "", height))

        def add_line():
            layout_elements.append(("line", "", None, "", 25))

        # --- 标题 ---
        add_text(f">> 性格分析 // {data.get('user_name', '未知')}", font_title, "#0230AC")
        add_space(15)

        # --- 基础标签 ---
        core = data.get("core_tags", {})
        shenren = core.get("shenren", {})
        suzhi = core.get("suzhi", {})
        mbti = core.get("mbti", {})
        animal = core.get("spirit_animal", {})

        add_text(f"[!] 神人值: {shenren.get('score', 0)} [{shenren.get('title', '')}]", font_sub, "#111111")
        add_space(4)
        add_text(f"[!] 素质水平: {suzhi.get('score', 0)} [{suzhi.get('title', '')}]", font_sub, "#111111")
        add_space(4)
        add_text(f"[!] MBTI: {mbti.get('type', '未知')}", font_sub, "#111111")
        add_space(4)
        add_text(f"[!] 兽设: {animal.get('name', '未知')}", font_sub, "#111111")
        add_space(10)

        # --- 性格标签 ---
        trait_tags = data.get("trait_tags", {})
        pros_tags = trait_tags.get("pros", [])
        cons_tags = trait_tags.get("cons", [])
        if pros_tags:
            add_text(f"优势标签：{'、'.join(pros_tags)}", font_body, "#0230AC")
            add_space(4)
        if cons_tags:
            add_text(f"缺点标签：{'、'.join(cons_tags)}", font_body, "#A31D1D")
            add_space(10)

        add_line()

        # --- 优势分析 ---
        add_text(">> 优势分析", font_title, "#0230AC")
        add_space(10)
        deep = data.get("deep_eval", {})
        for item in deep.get("pros", []):
            add_text(f"[+] {item.get('title', '')}", font_sub, "#0230AC")
            add_space(4)
            add_text(item.get("detail", ""), font_body, "#333333")
            add_space(12)

        add_line()

        # --- 缺点分析 ---
        add_text(">> 缺点分析", font_title, "#A31D1D")
        add_space(10)
        for item in deep.get("cons", []):
            add_text(f"[-] {item.get('title', '')}", font_sub, "#A31D1D")
            add_space(4)
            add_text(item.get("detail", ""), font_body, "#333333")
            add_space(12)

        add_line()

        # --- 相处建议 ---
        add_text(">> 相处建议", font_title, "#0230AC")
        add_space(10)
        for idx, adv in enumerate(data.get("verdict", []), 1):
            add_text(f"{idx}. {adv}", font_body, "#333333")
            add_space(6)

        # --- 动态画布绘制 ---
        text_height = sum([item[4] for item in layout_elements])
        total_h = top_h + text_height + bottom_h

        canvas = Image.new("RGBA", (base_w, total_h), (255, 255, 255, 255))
        canvas.paste(top_slice, (0, 0))
        canvas.paste(bottom_slice, (0, total_h - bottom_h))

        draw = ImageDraw.Draw(canvas)
        current_y = top_h

        for item_type, content, font, fill, delta in layout_elements:
            if item_type == "text":
                draw.text((margin_x, current_y), content, font=font, fill=fill)
                current_y += delta
            elif item_type == "space":
                current_y += delta
            elif item_type == "line":
                current_y += 10
                draw.line([(margin_x, current_y), (base_w - margin_x, current_y)], fill="#E5E5E5", width=2)
                draw.rectangle([(margin_x, current_y - 2), (margin_x + 8, current_y + 2)], fill="#0230AC")
                current_y += 15

        canvas.convert("RGB").save(output_path, "JPEG", quality=95)
