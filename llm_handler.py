import json
import asyncio
from astrbot.api import logger
from astrbot.api.star import Context


class CyberLLMHandler:
    def __init__(self, context: Context, config):
        self.context = context
        self.config = config

    async def analyze_history(self, user_name: str, logs: str, unified_msg_origin: str = "") -> dict:
        provider_id = self.config.get("llm_provider_id", "") or None
        pid = provider_id or await self.context.get_current_chat_provider_id(umo=unified_msg_origin)

        system_prompt = """你是一个群聊分析师，擅长从聊天记录中提炼人物画像。

【重要前提】：
- 这些消息是跨时间段提取的（可能跨越几天甚至几周），不是连续对话
- 因此"话题跳跃"是正常的，不要把话题变化当作缺点来评价
- 关注的是用户的说话风格、兴趣爱好、性格特点，而不是话题连贯性

【输出风格要求】：
- 像写人物分析报告一样，结构清晰、观点明确
- 每个优点/缺点单独成段，有小标题，有详细分析
- 分析中自然引用用户原话作为证据（用「」包裹），标注消息编号（如第XX条）
- 语气客观但不死板，可以适当毒舌点评，但不骂人不用脏话
- 每段分析 100-200 字，要有观点、有证据、有总结

【评分标准】：
- 神人值：衡量离谱/整活程度。普通人30-50，偶尔整活55-65，经常造梗70-80，真正的神人85+
- 素质水平：满嘴口癖50以下，正常聊天60-70，有礼貌有内容80+
- 大多数人神人值在30-60之间

【严格约束】：
1. 优势标签和缺点标签各 3-4 个词
2. 优势分析和缺点分析各 3-4 个小点，每个小点有标题和详细分析
3. 相处建议 3-5 条，具体可操作
4. 必须基于聊天记录中的实际内容分析，引用具体消息编号
5. 禁止评价"话题跳跃""表达碎片化""思维跳跃"等与话题连贯性相关的缺点

请严格按照以下 JSON 结构响应：
{
  "core_tags": {
    "shenren": {"score": 45, "title": "四字称号"},
    "suzhi": {"score": 65, "title": "四字称号"},
    "mbti": {"type": "INTJ"},
    "spirit_animal": {"name": "兽设名称"}
  },
  "trait_tags": {
    "pros": ["优势标签1", "优势标签2", "优势标签3"],
    "cons": ["缺点标签1", "缺点标签2", "缺点标签3"]
  },
  "deep_eval": {
    "pros": [
      {"title": "优点小标题", "detail": "100-200字详细分析，自然引用原话和消息编号"},
      {"title": "优点小标题", "detail": "100-200字详细分析，自然引用原话和消息编号"},
      {"title": "优点小标题", "detail": "100-200字详细分析，自然引用原话和消息编号"}
    ],
    "cons": [
      {"title": "缺点小标题", "detail": "100-200字详细分析，自然引用原话和消息编号"},
      {"title": "缺点小标题", "detail": "100-200字详细分析，自然引用原话和消息编号"},
      {"title": "缺点小标题", "detail": "100-200字详细分析，自然引用原话和消息编号"}
    ]
  },
  "verdict": ["具体相处建议1", "具体相处建议2", "具体相处建议3", "具体相处建议4", "具体相处建议5"]
}"""

        prompt = f"请对以下用户「{user_name}」的群聊记录进行性格分析：\n\n{logs}"

        last_error = None
        for attempt in range(3):
            try:
                llm_resp = await self.context.llm_generate(
                    chat_provider_id=pid,
                    prompt=prompt,
                    system_prompt=system_prompt,
                )

                raw_text = llm_resp.completion_text.strip()

                if not raw_text:
                    logger.warning(f"[赛博案底] 第{attempt+1}次尝试: LLM返回为空，重试中...")
                    await asyncio.sleep(2)
                    continue

                if raw_text.startswith("```json"):
                    raw_text = raw_text.split("```json")[-1].split("```")[0].strip()
                if raw_text.startswith("```"):
                    raw_text = raw_text.strip("```").strip()

                parsed_data = json.loads(raw_text)
                parsed_data["user_name"] = user_name
                return parsed_data

            except json.JSONDecodeError as e:
                logger.warning(f"[赛博案底] 第{attempt+1}次尝试: JSON解析失败，重试中...")
                logger.debug(f"[赛博案底] 原始返回: {raw_text[:500]}")
                last_error = e
                await asyncio.sleep(2)
                continue
            except Exception as e:
                last_error = e
                logger.warning(f"[赛博案底] 第{attempt+1}次尝试失败: {e}")
                await asyncio.sleep(2)
                continue

        raise ValueError(f"LLM调用失败(已重试3次): {last_error}")