from typing import Any

from openai import OpenAI, OpenAIError

from backend.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from backend.services.context_cleaner import clean_contexts


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
            "content": build_system_prompt(),
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
    cleaned_contexts = clean_contexts(question, contexts)
    context_text = format_contexts(cleaned_contexts)
    if not context_text:
        context_text = "知识库中未检索到充分依据，以下仅为通用建议。"

    return (
        f"用户问题：{question}\n\n"
        f"已清洗的 RAG 上下文（按 Hybrid Search 相关性排序，已截取相关句并去重）：\n{context_text}\n\n"
        "请输出现场可执行的检修 SOP。不要输出大段理论解释，不要使用“根据您的问题”“综合分析”等 AI 话术。"
    )


def build_system_prompt() -> str:
    return (
        "你是设备检修作业辅助专家，输出必须像工业维修 SOP、现场操作卡。"
        "必须优先依据已清洗的知识片段回答，优先使用 final_score、keyword_hits、bm25_score 高的片段。"
        "不得编造手册没有的步骤、参数、扭矩、间隙、零件型号。"
        "知识片段不足时，必须写明：知识库中未检索到充分依据，以下仅为通用建议。"
        "输出要短、准、可执行，避免理论展开和免责声明堆叠。"
        "固定输出以下六部分："
        "一、问题判断；二、可能原因；三、标准检查步骤；四、标准作业步骤；五、安全与合规提醒；六、参考依据。"
        "检查步骤和作业步骤必须使用“步骤1：”“步骤2：”“步骤3：”格式，每步只写一个动作或判断。"
        "每个重要步骤后尽量标注来源，格式：【来源：文件名，第X页】。"
        "参考依据部分列出文件名、页码、chunk_id。"
        "涉及发动机、通电、拆卸、安装、高温、旋转部件时，必须提醒停机断电、防烫伤、防夹伤、"
        "使用专用或合适工具、扭矩按手册要求执行，不确定时由专业人员操作。"
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
