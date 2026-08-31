import unittest

from app.retrieval.hybrid_search import SearchResult
from app.retrieval.reranker import RankedChunk, RerankPlan, apply_rerank_plan, local_rerank_results


def result(chunk_id: int) -> SearchResult:
    return SearchResult(chunk_id, 1, 1, str(chunk_id), "text", 1, None, 0.0, 0.5)


class RerankerTest(unittest.TestCase):
    def test_reorders_and_rejects_unknown_chunk(self):
        plan = RerankPlan(rankings=[
            RankedChunk(chunk_id=99, relevance=3, reason="unknown"),
            RankedChunk(chunk_id=2, relevance=3, reason="best"),
            RankedChunk(chunk_id=1, relevance=1, reason="weak"),
        ])
        ranked = apply_rerank_plan([result(1), result(2), result(3)], plan, 3)
        self.assertEqual([item.chunk_id for item in ranked], [2, 1, 3])

    def test_deduplicates_model_output(self):
        plan = RerankPlan(rankings=[
            RankedChunk(chunk_id=1, relevance=3, reason="a"),
            RankedChunk(chunk_id=1, relevance=2, reason="b"),
        ])
        ranked = apply_rerank_plan([result(1), result(2)], plan, 2)
        self.assertEqual([item.chunk_id for item in ranked], [1, 2])

    def test_local_rerank_handles_vietnamese_without_accents(self):
        candidates = [result(1), result(2)]
        candidates[0].content = "noi dung khac"
        candidates[1].content = "Hàm đệ quy cần điều kiện dừng"
        ranked = local_rerank_results("ham de quy", candidates, 2)
        self.assertEqual(ranked[0].chunk_id, 2)


if __name__ == "__main__":
    unittest.main()
