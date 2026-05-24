import re
from typing import Any

MAX_CONTEXT_CHARS = 500
MAX_TOTAL_CONTEXT_CHARS = 1800
SENTENCE_WINDOW = 1
MIN_KEYWORD_LENGTH = 2
SIMILARITY_THRESHOLD = 0.82

INDUSTRIAL_TERMS = {
    "安装",
    "拆卸",
    "更换",
    "检查",
    "调整",
    "固定",
    "锁紧",
    "紧固",
    "拧紧",
    "扭矩",
    "防松",
    "顺序",
    "离合器",
    "发动机",
    "火花塞",
    "机油",
    "螺母",
    "螺栓",
    "曲轴",
    "通电",
    "停机",
    "断电",
    "专用工具",
}
STOP_WORDS = {
    "如何",
    "怎么",
    "怎么办",
    "什么",
    "多少",
    "进行",
    "需要",
    "一下",
}


def clean_contexts(question: str, contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keywords = extract_keywords(question)
    cleaned_contexts: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()
    seen_sentences: list[str] = []
    total_chars = 0

    for context in contexts:
        chunk_id = str(context.get("chunk_id", ""))
        if chunk_id and chunk_id in seen_chunk_ids:
            continue
        if chunk_id:
            seen_chunk_ids.add(chunk_id)

        content = str(context.get("content", ""))
        related_text = extract_related_text(content, keywords)
        deduped_text = deduplicate_text(related_text, seen_sentences)
        compact_text = compact_text_length(deduped_text, MAX_CONTEXT_CHARS)
        if not compact_text:
            continue

        next_total = total_chars + len(compact_text)
        if next_total > MAX_TOTAL_CONTEXT_CHARS:
            remaining = MAX_TOTAL_CONTEXT_CHARS - total_chars
            if remaining <= 0:
                break
            compact_text = compact_text_length(compact_text, remaining)

        cleaned_contexts.append(
            {
                **context,
                "content": compact_text,
                "original_content_length": len(content),
                "cleaned_content_length": len(compact_text),
            }
        )
        total_chars += len(compact_text)

        if total_chars >= MAX_TOTAL_CONTEXT_CHARS:
            break

    return cleaned_contexts


def extract_keywords(question: str) -> set[str]:
    normalized = normalize_text(question)
    words = {
        word
        for word in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]{2,}", normalized)
        if word not in STOP_WORDS and len(word) >= MIN_KEYWORD_LENGTH
    }
    words.update(term for term in INDUSTRIAL_TERMS if term in normalized)
    return words


def extract_related_text(content: str, keywords: set[str]) -> str:
    normalized_content = normalize_text(content)
    sentences = split_sentences(normalized_content)
    if not sentences:
        return compact_text_length(normalized_content, MAX_CONTEXT_CHARS)

    matched_indices = {
        index
        for index, sentence in enumerate(sentences)
        if sentence_matches(sentence, keywords)
    }
    if not matched_indices:
        return compact_text_length("。".join(sentences[:3]), MAX_CONTEXT_CHARS)

    selected_indices: set[int] = set()
    for index in matched_indices:
        selected_indices.add(index)
        for neighbor_index in range(
            max(index - SENTENCE_WINDOW, 0),
            min(index + SENTENCE_WINDOW + 1, len(sentences)),
        ):
            if neighbor_index == index:
                continue
            if is_useful_neighbor_sentence(sentences[neighbor_index], keywords):
                selected_indices.add(neighbor_index)

    selected_sentences = [sentences[index] for index in sorted(selected_indices)]
    return "。".join(selected_sentences)


def split_sentences(text: str) -> list[str]:
    fragments = re.split(r"(?<=[。！？；;.!?])\s*|\n+", text)
    return [fragment.strip(" 。；;") for fragment in fragments if fragment.strip(" 。；;")]


def sentence_matches(sentence: str, keywords: set[str]) -> bool:
    if any(keyword in sentence for keyword in keywords):
        return True
    return any(term in sentence for term in INDUSTRIAL_TERMS)


def is_useful_neighbor_sentence(sentence: str, keywords: set[str]) -> bool:
    if sentence_matches(sentence, keywords):
        return True
    return bool(re.search(r"\d+\s*(n·m|nm|mm|毫米|%)", sentence.lower()))


def deduplicate_text(text: str, seen_sentences: list[str]) -> str:
    unique_sentences: list[str] = []
    for sentence in split_sentences(text):
        if is_similar_to_seen(sentence, seen_sentences) or is_similar_to_seen(sentence, unique_sentences):
            continue
        unique_sentences.append(sentence)
        seen_sentences.append(sentence)
    return "。".join(unique_sentences)


def is_similar_to_seen(sentence: str, seen_sentences: list[str]) -> bool:
    return any(calculate_similarity(sentence, seen) >= SIMILARITY_THRESHOLD for seen in seen_sentences)


def calculate_similarity(left: str, right: str) -> float:
    left_units = get_text_units(left)
    right_units = get_text_units(right)
    if not left_units or not right_units:
        return 0.0
    return len(left_units & right_units) / len(left_units | right_units)


def get_text_units(text: str) -> set[str]:
    normalized = normalize_text(text)
    if len(normalized) <= 2:
        return {normalized} if normalized else set()
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def compact_text_length(text: str, max_chars: int) -> str:
    stripped_text = text.strip()
    if len(stripped_text) <= max_chars:
        return stripped_text
    return f"{stripped_text[:max_chars].rstrip()}..."


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
