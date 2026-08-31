import unittest

from app.retrieval.bounded_retrieval import SearchQueryPlan, _normalize_queries, fuse_search_results
from app.retrieval.hybrid_search import SearchResult


def result(chunk_id: int) -> SearchResult:
    return SearchResult(chunk_id, 1, 1, str(chunk_id), "text", 1, None, 0.0, 0.5)


class BoundedRetrievalTest(unittest.TestCase):
    def test_original_query_is_always_first_and_deduplicated(self):
        plan = SearchQueryPlan(semantic_query="Python list", keyword_query="list mutable", course_query=None)
        queries = _normalize_queries("Python list", plan, 3)
        self.assertEqual(queries, ["Python list", "list mutable"])

    def test_query_budget_is_capped_at_three(self):
        plan = SearchQueryPlan(semantic_query="bb", keyword_query="cc", course_query="dd")
        self.assertEqual(len(_normalize_queries("a", plan, 99)), 3)

    def test_rrf_rewards_chunk_seen_in_multiple_lists(self):
        fused = fuse_search_results([[result(1), result(2)], [result(2), result(3)]], 3)
        self.assertEqual(fused[0].chunk_id, 2)
        self.assertEqual({item.chunk_id for item in fused}, {1, 2, 3})


if __name__ == "__main__":
    unittest.main()
