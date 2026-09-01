import asyncio
import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from app.auth.dependencies import require_role
from app.internal_learning.service import load_modules, search_modules


class InternalLearningTests(unittest.TestCase):
    def test_internal_course_has_complete_modules_and_quizzes(self) -> None:
        modules = load_modules()
        self.assertGreaterEqual(len(modules), 51)
        self.assertTrue(all(module["sections"] for module in modules))
        self.assertTrue(all(module["quiz"] for module in modules))

    def test_internal_search_finds_agentic_rag_without_exposing_all_modules(self) -> None:
        results = search_modules("agentic rag pipeline hai bước", limit=2)
        self.assertTrue(results)
        self.assertEqual(results[0]["id"], "agentic-rag")
        self.assertLessEqual(len(results), 2)

    def test_owner_dependency_accepts_only_owner_role(self) -> None:
        checker = require_role("OWNER")
        owner = asyncio.run(checker(user=SimpleNamespace(role="OWNER")))
        self.assertEqual(owner.role, "OWNER")

        with self.assertRaises(HTTPException) as forbidden:
            asyncio.run(checker(user=SimpleNamespace(role="ADMIN")))
        self.assertEqual(forbidden.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
