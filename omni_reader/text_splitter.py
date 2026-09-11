"""Intelligent text cleaning and sentence splitting for streaming TTS."""

import re
from typing import List

# Common abbreviations that should not trigger sentence boundaries
ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "etc",
    "ie", "eg", "al", "fig", "approx", "dept", "est", "min", "max",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "st", "ave", "blvd", "rd", "no", "corp", "inc", "ltd", "co"
}


def clean_markdown_and_text(text: str) -> str:
    """Cleans up markdown formatting, URLs, and excessive symbols for natural speech."""
    if not text:
        return ""

    # Replace smart quotes and special apostrophes
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = text.replace("—", ", ").replace("–", ", ")

    # Remove markdown image tags ![alt](url) -> ""
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

    # Markdown links [text](url) -> text
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)

    # Strip standalone URLs (replace with domain)
    text = re.sub(r'https?://(?:www\.)?(\S+)', r'\1', text)
    text = re.sub(r'([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/\S*', r'\1', text)

    # Markdown headers (# Header) -> Header
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Bold/Italic formatting (*text* or **text** or _text_) -> text
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}(.*?)_{1,3}', r'\1', text)

    # Inline code `code` -> code
    text = re.sub(r'`+(.*?)`+', r'\1', text)

    # Strip code block fences
    text = re.sub(r'```[a-zA-Z0-9_-]*\n?', '', text)

    # Bullet lists (- item, * item, 1. item) -> item
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # Normalize excessive symbols and spaces
    text = re.sub(r'[-=_*]{3,}', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{2,}', '\n\n', text)

    return text.strip()


def is_abbreviation(word: str) -> bool:
    """Checks if a dot-ending token is a known abbreviation, acronym, or single initial."""
    clean_w = word.strip().strip('"\'()[]{}')
    if not clean_w.endswith("."):
        return False

    # Acronyms with periods like U.S., U.K., e.g., i.e., Ph.D., A.I.
    if re.match(r'^([a-zA-Z]\.)+$', clean_w, re.IGNORECASE):
        return True

    token = clean_w.lower().rstrip(".").strip()
    if token in ABBREVIATIONS:
        return True
    if len(token) == 1 and token.isalpha():  # Middle initials like "John F. Kennedy"
        return True
    return False


def split_sentences(text: str, max_words_per_chunk: int = 50) -> List[str]:
    """
    Splits text into streamable sentences or clauses.
    Preserves abbreviations and decimal numbers.
    """
    cleaned = clean_markdown_and_text(text)
    if not cleaned:
        return []

    # Paragraph split first
    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    chunks: List[str] = []

    for para in paragraphs:
        # Candidate split by sentence punctuation followed by whitespace
        # (?<=[.!?])\s+
        raw_tokens = re.split(r'(\s+)', para)
        
        current_sentence: List[str] = []
        for i in range(0, len(raw_tokens), 2):
            word = raw_tokens[i]
            space = raw_tokens[i + 1] if i + 1 < len(raw_tokens) else ""
            current_sentence.append(word)

            # Check if this word ends with sentence punctuation
            if word and word[-1] in ".!?":
                # Check for decimals (e.g. "3.14")
                if re.match(r'^\d+\.\d+$', word):
                    if space:
                        current_sentence.append(space)
                    continue

                # Check for abbreviation
                if word.endswith(".") and is_abbreviation(word):
                    if space:
                        current_sentence.append(space)
                    continue

                # Valid sentence end
                sentence_str = "".join(current_sentence).strip()
                if sentence_str:
                    chunks.append(sentence_str)
                current_sentence = []
            else:
                if space:
                    current_sentence.append(space)

        leftover = "".join(current_sentence).strip()
        if leftover:
            chunks.append(leftover)

    # Subdivide any overly long run-on sentences (> max_words_per_chunk) by semicolons or commas
    final_chunks: List[str] = []
    for chunk in chunks:
        words = chunk.split()
        if len(words) > max_words_per_chunk:
            # Split by semicolon or colon first
            subparts = re.split(r'(?<=[;:])\s+', chunk)
            for subpart in subparts:
                sub_words = subpart.split()
                if len(sub_words) > max_words_per_chunk:
                    # Split by comma
                    comma_parts = re.split(r'(?<=[,])\s+', subpart)
                    accum = []
                    for cp in comma_parts:
                        accum.append(cp)
                        if len(" ".join(accum).split()) >= 25:
                            final_chunks.append(" ".join(accum).strip())
                            accum = []
                    if accum:
                        final_chunks.append(" ".join(accum).strip())
                else:
                    if subpart.strip():
                        final_chunks.append(subpart.strip())
        else:
            if chunk.strip():
                final_chunks.append(chunk.strip())

    return [c for c in final_chunks if c.strip()]
