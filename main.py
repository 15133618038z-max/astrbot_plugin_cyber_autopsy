import os
import re
import asyncio
from collections import defaultdict, deque
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.api import AstrBotConfig, logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from .llm_handler import CyberLLMHandler
from .image_renderer import CyberImageRenderer


class CyberAutopsyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self.llm_handler = CyberLLMHandler(self.context, self.config)
        self.max_msgs = self.config.get("max_analysis_messages", 100)
        self.history = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=self.max_msgs))
        )
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.assets_dir = os.path.join(self.current_dir, "assets")
        self.output_dir = os.path.join(self.current_dir, "output")
        self.bg_path = os.path.join(self.assets_dir, "bg.jpg")
        self.font_path = os.path.join(self.assets_dir, "font.ttf")
        # 排队机制：同时只处理 1 个画像任务
        self._queue = asyncio.Queue()
        self._processing = False

    async def initialize(self):
        os.makedirs(self.assets_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        if not os.path.exists(self.bg_path):
            logger.warning(f"[赛博案底] 警告: 未找到底图。请将底图重命名为 bg.jpg 并放入 {self.assets_dir} 文件夹。")
        if not os.path.exists(self.font_path):
            logger.warning(f"[赛博案底] 警告: 未找到字体。请将字体文件重命名为 font.ttf 并放入 {self.assets_dir} 文件夹。")

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_message(self, event: AiocqhttpMessageEvent):
        msg_str = event.message_str.strip()
        if msg_str.startswith("画像"):
            async for result in self._process_profile_command(event):
                yield result
            return
        if msg_str and not msg_str.startswith("/"):
            group_id = str(event.get_group_id())
            sender_id = str(event.get_sender_id())
            self.history[group_id][sender_id].append(msg_str)

    async def _fetch_history_from_qq(
        self, event: AiocqhttpMessageEvent, group_id: str, user_id: str
    ) -> list:
        target_messages = []
        max_rounds = 25
        message_seq = 0

        try:
            for round_num in range(max_rounds):
                resp = await event.bot.api.call_action(
                    "get_group_msg_history",
                    group_id=group_id,
                    message_seq=message_seq,
                    count=200,
                    reverseOrder=True,
                )

                batch = resp.get("messages", [])
                if not batch:
                    break

                for msg in batch:
                    sender_id = str(msg.get("sender", {}).get("user_id", ""))
                    if sender_id != user_id:
                        continue
                    for seg in msg.get("message", []):
                        if seg.get("type") == "text":
                            text = seg.get("data", {}).get("text", "").strip()
                            if text and not text.startswith("/"):
                                target_messages.append(text)

                if len(target_messages) >= self.max_msgs:
                    break

                next_seq = batch[0].get("message_seq", 0)
                if next_seq == message_seq:
                    break
                message_seq = next_seq

                logger.info(f"[赛博案底] 第{round_num+1}页完成, 累计{len(target_messages)}条")
                await asyncio.sleep(0.5)

        except Exception as e:
            logger.warning(f"[赛博案底] 拉取历史消息中断(已获取{len(target_messages)}条): {e}")

        logger.info(f"[赛博案底] 最终获取目标用户消息: {len(target_messages)}条")
        return target_messages[-self.max_msgs:]

    async def _process_profile_command(self, event: AiocqhttpMessageEvent):
        target_user_id = None
        target_user_name = "神秘群友"

        match = re.search(r'画像\s*(\d{5,12})', event.message_str.strip())
        if match:
            target_user_id = match.group(1)

        if not target_user_id:
            yield event.plain_result("用法错误：请使用「画像QQ号」，例如：画像20743692")
            return

        protected_list = [str(q) for q in self.config.get("protected_qq_list", [])]
        if target_user_id in protected_list:
            yield event.plain_result("该用户受保护，无法生成画像。")
            return

        # 排队机制
        if self._processing:
            yield event.plain_result("当前有画像正在生成中，已加入排队，请稍候...")
            while self._processing:
                await asyncio.sleep(1)

        self._processing = True
        try:
            for _ in range(3):
                try:
                    info = await event.bot.get_group_member_info(
                        group_id=int(event.get_group_id()),
                        user_id=int(target_user_id),
                        no_cache=False,
                    )
                    target_user_name = info.get("card") or info.get("nickname", "神秘群友")
                    break
                except Exception:
                    await asyncio.sleep(1)
            else:
                logger.warning(f"[赛博案底] 获取用户昵称失败，使用默认值")

            group_id = str(event.get_group_id())
            history_msgs = await self._fetch_history_from_qq(event, group_id, target_user_id)
            await asyncio.sleep(1)
            cached_msgs = list(self.history[group_id].get(target_user_id, []))
            seen = set()
            merged = []
            for msg in history_msgs + cached_msgs:
                if msg not in seen:
                    seen.add(msg)
                    merged.append(msg)
            merged = merged[-self.max_msgs:]

            if len(merged) < 5:
                yield event.plain_result(f"样本不足：该用户近期发言太少(仅{len(merged)}条)，可不无法生成高精度画像。")
                return

            yield event.plain_result(f"正在调取该用户的 {len(merged)} 条赛博案底，可不开始审判...")

            try:
                logs_text = "\n".join([f"[{i+1}]: {msg}" for i, msg in enumerate(merged)])
                analysis_data = await self.llm_handler.analyze_history(
                    target_user_name, logs_text, event.unified_msg_origin
                )
                renderer = CyberImageRenderer(self.bg_path, self.font_path)
                output_path = os.path.join(self.output_dir, f"autopsy_{target_user_id}.jpg")
                renderer.render(analysis_data, output_path)
                if os.path.exists(output_path):
                    yield event.image_result(output_path)
                    os.remove(output_path)
                else:
                    yield event.plain_result("图片渲染组件故障。")
            except Exception as e:
                logger.error(f"画像生成崩溃: {str(e)}")
                yield event.plain_result(f"生成中断。错误代码: {str(e)}")
        finally:
            self._processing = False
