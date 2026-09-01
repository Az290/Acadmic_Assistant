import json
import re
from functools import lru_cache
from pathlib import Path


CONTENT_PATHS = (
    Path(__file__).with_name("content.json"),
    Path(__file__).with_name("content_advanced.json"),
    Path(__file__).with_name("content_junior_foundations.json"),
    Path(__file__).with_name("content_junior_deep_learning.json"),
    Path(__file__).with_name("content_junior_agents.json"),
    Path(__file__).with_name("content_junior_mlops_career.json"),
    Path(__file__).with_name("content_junior_extended.json"),
    Path(__file__).with_name("content_junior_electives.json"),
)


@lru_cache(maxsize=1)
def load_modules() -> list[dict]:
    modules: list[dict] = []
    for content_path in CONTENT_PATHS:
        with content_path.open("r", encoding="utf-8") as content_file:
            modules.extend(json.load(content_file))
    return modules


def search_modules(query: str, *, limit: int = 3) -> list[dict]:
    """Tìm kiếm lexical có trọng số trong kho nhỏ; không gửi nội dung ra ngoài OWNER."""
    terms = {term for term in re.findall(r"[\wÀ-ỹ]+", query.casefold()) if len(term) > 1}
    ranked: list[tuple[int, dict]] = []
    for module in load_modules():
        title_text = f"{module['title']} {module['summary']}".casefold()
        full_text = json.dumps(module, ensure_ascii=False).casefold()
        score = sum(4 for term in terms if term in title_text) + sum(1 for term in terms if term in full_text)
        if score:
            ranked.append((score, module))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = ranked[: max(1, min(limit, 4))]
    return [
        {
            "id": module["id"],
            "title": module["title"],
            "summary": module["summary"],
            "sections": [
                {
                    "title": section["title"],
                    "body": section["body"],
                    "project_example": section["projectExample"],
                    "why": section["why"],
                    "alternatives": section.get("alternatives", []),
                }
                for section in module["sections"]
            ],
        }
        for _, module in selected
    ]
