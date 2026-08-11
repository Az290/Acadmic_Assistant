"""
Tính lại vector cho toàn bộ chunk + document đang dùng model embedding CŨ.

KHI NÀO CẦN CHẠY: mỗi lần đổi model embedding (EMBEDDING_VERSION trong
app/ingestion/embedder.py thay đổi).

VÌ SAO BẮT BUỘC: vector sinh từ 2 model khác nhau nằm trong 2 "không
gian toạ độ" hoàn toàn khác nhau - so sánh cosine giữa chúng cho kết
quả VÔ NGHĨA (không phải sai lệch nhẹ, mà là hoàn toàn ngẫu nhiên).
Nếu chỉ đổi model mà không tính lại dữ liệu cũ, tìm kiếm sẽ trả về kết
quả rác một cách âm thầm - không có thông báo lỗi nào.

Chạy: python scripts/reindex_embeddings.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select  # noqa: E402

from app.db.models import Chunk, Concept, Document  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.ingestion.embedder import EMBEDDING_VERSION, embed_texts  # noqa: E402

# Xử lý theo lô để không nạp toàn bộ chunk vào bộ nhớ cùng lúc, và để
# thấy tiến độ khi chạy trên dữ liệu lớn.
BATCH_SIZE = 100


async def main() -> None:
    async with AsyncSessionLocal() as session:
        stale_chunks = (
            await session.execute(
                select(Chunk).where(Chunk.embedding_version != EMBEDDING_VERSION)
            )
        ).scalars().all()

        print(f"Model hiện tại: {EMBEDDING_VERSION}")
        print(f"Số chunk cần tính lại: {len(stale_chunks)}")

        for start in range(0, len(stale_chunks), BATCH_SIZE):
            batch = stale_chunks[start : start + BATCH_SIZE]
            vectors = await asyncio.to_thread(embed_texts, [c.content for c in batch])
            for chunk, vector in zip(batch, vectors):
                chunk.embedding = vector
                chunk.embedding_version = EMBEDDING_VERSION
            await session.commit()
            print(f"  Đã xử lý {min(start + BATCH_SIZE, len(stale_chunks))}/{len(stale_chunks)} chunk")

        # Vector đại diện của document = trung bình cộng vector các chunk
        # của nó (dùng cho phát hiện tài liệu gần trùng, xem
        # app/curator/dedup.py) - phải tính lại theo đúng vector MỚI.
        documents = (await session.execute(select(Document))).scalars().all()
        print(f"\nTính lại vector đại diện cho {len(documents)} tài liệu...")

        for document in documents:
            chunk_vectors = (
                await session.execute(
                    select(Chunk.embedding).where(
                        Chunk.document_id == document.id, Chunk.embedding.is_not(None)
                    )
                )
            ).scalars().all()

            if not chunk_vectors:
                continue

            dimension = len(chunk_vectors[0])
            document.embedding = [
                sum(v[i] for v in chunk_vectors) / len(chunk_vectors) for i in range(dimension)
            ]

        # Vector TÊN KHÁI NIỆM - dùng để nhận diện câu hỏi thuộc chủ đề
        # nào (xem app/learning/concept_matcher.py).
        #
        # KHÔNG ĐƯỢC QUÊN BẢNG NÀY (đã từng bỏ sót và phải sửa): nếu chỉ
        # tính lại chunk mà bỏ concept, việc so khớp sẽ đem vector câu
        # hỏi (model MỚI) so với vector khái niệm (model CŨ) - hai không
        # gian toạ độ khác nhau, kết quả hoàn toàn vô nghĩa và luôn trả
        # về "không khớp khái niệm nào", âm thầm không báo lỗi.
        concepts = (await session.execute(select(Concept))).scalars().all()
        print(f"\nTính lại vector cho {len(concepts)} khái niệm...")

        if concepts:
            concept_vectors = await asyncio.to_thread(embed_texts, [c.name for c in concepts])
            for concept, vector in zip(concepts, concept_vectors):
                concept.embedding = vector

        await session.commit()
        print("Xong.")


if __name__ == "__main__":
    asyncio.run(main())
