from typing import Any

from openai import OpenAI, OpenAIError

from backend.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL


def generate_repair_answer(question: str, contexts: list[dict[str, Any]]) -> str:
    if not QWEN_API_KEY:
        raise RuntimeError("QWEN_API_KEY 未配置")

    client = OpenAI(
        api_key=QWEN_API_KEY,
        base_url=QWEN_BASE_URL,
    )

    messages = [
        {
            "role": "system",
            "content": (
                "你是设备检修知识检索与作业系统的专业检修助手。"
                "请仅基于给定知识库上下文回答问题，不要编造未提供的设备参数、维修结论或安全规范。"
                "回答必须包含四个小节：1. 可能原因；2. 检查步骤；3. 安全提醒；4. 参考依据。"
                "如果上下文不足，请明确说明“知识库中未检索到充分依据”，并给出保守的通用检查建议。"
            ),
        },
        {
            "role": "user",
            "content": build_user_prompt(question, contexts),
        },
    ]

    try:
        response = client.chat.completions.create(
            model=QWEN_MODEL,
            messages=messages,
            temperature=0.2,
        )
    except OpenAIError as exc:
        raise RuntimeError("Qwen API 调用失败") from exc

    answer = response.choices[0].message.content
    if not answer:
        raise RuntimeError("Qwen API 未返回有效回答")

    return answer


def build_user_prompt(question: str, contexts: list[dict[str, Any]]) -> str:
    context_text = format_contexts(contexts)
    if not context_text:
        context_text = "知识库中未检索到充分依据。"

    return (
        f"用户问题：{question}\n\n"
        f"知识库检索上下文：\n{context_text}\n\n"
        "请面向设备检修作业人员，用清晰、可执行、谨慎的中文回答。"
    )


def format_contexts(contexts: list[dict[str, Any]]) -> str:
    if not contexts:
        return ""

    formatted_contexts: list[str] = []
    for index, context in enumerate(contexts, start=1):
        filename = context.get("filename", "未知文件")
        page = context.get("page", "未知页码")
        chunk_id = context.get("chunk_id", "未知片段")
        content = context.get("content", "")
        formatted_contexts.append(
            f"[{index}] 文件：{filename}；页码：{page}；片段：{chunk_id}\n{content}"
        )

    return "\n\n".join(formatted_contexts)
