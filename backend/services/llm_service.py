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
                "你是设备检修作业辅助专家，服务于工业维修、装配、拆卸、检查、调整等现场作业。"
                "必须优先依据用户问题下方给出的知识库检索片段回答。"
                "检索片段来自 Hybrid Search，请优先参考 final_score、keyword_hits、bm25_score 较高的片段，"
                "再结合 semantic_score 判断相关性。"
                "不要编造手册中没有的步骤、参数、扭矩、间隙、零件型号或安全规范。"
                "如果知识片段不足，必须明确写出“知识库中未检索到充分依据，以下仅为通用建议。”"
                "回答必须结构化，并严格包含：一、问题判断；二、可能原因；三、标准检查步骤；"
                "四、标准作业步骤；五、安全与合规提醒；六、参考依据。"
                "参考依据中必须尽量引用文件名、页码和 chunk_id，例如："
                "《摩托车发动机维修手册.pdf》第 26 页，chunk_id: xxx。"
                "如果涉及拆卸、安装、通电、发动机运行等作业，必须提醒停机断电、防烫伤、防夹伤、"
                "使用合适工具、扭矩按手册要求执行、不确定时由专业人员操作。"
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
        context_text = "知识库中未检索到充分依据，以下仅为通用建议。"

    return (
        f"用户问题：{question}\n\n"
        f"知识库检索上下文（已按 Hybrid Search 综合相关性排序）：\n{context_text}\n\n"
        "请面向设备检修作业人员，用清晰、可执行、谨慎的中文回答。"
        "若上下文与问题不匹配，请降低其参考权重，并明确说明依据不足。"
    )


def format_contexts(contexts: list[dict[str, Any]]) -> str:
    if not contexts:
        return ""

    formatted_contexts: list[str] = []
    for index, context in enumerate(contexts, start=1):
        filename = context.get("filename", "未知文件")
        page = context.get("page", "未知页码")
        chunk_id = context.get("chunk_id", "未知片段")
        final_score = context.get("final_score", "无")
        keyword_hits = context.get("keyword_hits", "无")
        bm25_score = context.get("bm25_score", "无")
        semantic_score = context.get("semantic_score", "无")
        content = context.get("content", "")
        formatted_contexts.append(
            f"[{index}] 文件：{filename}；页码：{page}；chunk_id：{chunk_id}；"
            f"final_score：{final_score}；keyword_hits：{keyword_hits}；"
            f"bm25_score：{bm25_score}；semantic_score：{semantic_score}\n{content}"
        )

    return "\n\n".join(formatted_contexts)
