from pathlib import Path
from langchain_text_splitters import MarkdownHeaderTextSplitter


RAW_DATA_DIR = Path("data/")
KNOWLEDGE_FILE = RAW_DATA_DIR / "knowledge.md"

# Each ## heading represents an independent approved support topic in the provided knowledge base, so we preserve those boundaries.
HEADERS_TO_SPLIT_ON = [
    ("##", "section"),
]


def load_markdown(file_path: Path) -> str:
    """Reads the markdown file from disk and returns the raw text."""
    if not file_path.exists():
        raise FileNotFoundError(
            f"Could not find knowledge base file at: {file_path.resolve()}"
        )
    return file_path.read_text(encoding="utf-8")


def chunk_markdown(markdown_text: str):
    """
    Splits the markdown text on '##' headings.
    Each returned chunk has .page_content (the section text) and
    .metadata (which includes the section heading, so we know later
    which topic a retrieved chunk belongs to).
    """
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS_TO_SPLIT_ON)
    return splitter.split_text(markdown_text)


# def print_chunks(chunks) -> None:
#     """Prints each chunk to console so we can sanity check the split."""
#     print(f"Total chunks created: {len(chunks)}\n")

#     for i, chunk in enumerate(chunks, start=1):
#         section_name = chunk.metadata.get("section", "Untitled / preamble")
#         print(f"--- Chunk {i} ---")
#         print(f"Section: {section_name}")
#         print(f"Length: {len(chunk.page_content)} chars")
#         print(chunk.page_content.strip())
#         print()


# def main():
#     raw_text = load_markdown(KNOWLEDGE_FILE)
#     chunks = chunk_markdown(raw_text)
#     print_chunks(chunks)


# if __name__ == "__main__":
#     main()