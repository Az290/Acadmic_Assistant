"""
Eval Dashboard - trang xem lịch sử chất lượng hệ thống qua các lượt
chạy scripts/eval.py (Router category accuracy, Retrieval Recall@K,
LLM-judge score) theo THỜI GIAN, để phát hiện SỚM khi 1 thay đổi code
làm giảm chất lượng thay vì chỉ biết được lúc người dùng thật phàn nàn.

CHỈ ADMIN xem được (đã chốt cùng người dùng) - khác Dashboard giảng
viên (app/instructor/router.py, xem theo LỚP mình phụ trách), đây là
số liệu vận hành TOÀN HỆ THỐNG, không thuộc phạm vi 1 giảng viên.

KHÔNG có endpoint xoá - EvalRun giữ lại vĩnh viễn để so sánh xu hướng
dài hạn, kể cả lượt chạy có điểm thấp (xem app/db/models.py::EvalRun).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import require_role
from app.db.models import AppUser, EvalRun
from app.db.session import get_db
from app.eval_dashboard.schemas import EvalRunDetail, EvalRunSummary

router = APIRouter(prefix="/v1/eval-dashboard", tags=["eval-dashboard"])


@router.get("/runs", response_model=list[EvalRunSummary])
async def list_eval_runs(
    session: AsyncSession = Depends(get_db),
    _user: AppUser = Depends(require_role("ADMIN")),
):
    """Danh sách các lượt eval, MỚI NHẤT TRƯỚC - đủ dữ liệu để vẽ biểu đồ xu hướng."""
    rows = (await session.execute(select(EvalRun).order_by(EvalRun.created_at.desc()))).scalars().all()
    return rows


@router.get("/runs/{run_id}", response_model=EvalRunDetail)
async def get_eval_run_detail(
    run_id: int,
    session: AsyncSession = Depends(get_db),
    _user: AppUser = Depends(require_role("ADMIN")),
):
    """Chi tiết 1 lượt eval - từng câu hỏi mẫu kèm judge_reasoning để tra cứu lý do cụ thể."""
    run = (
        await session.execute(
            select(EvalRun).where(EvalRun.id == run_id).options(selectinload(EvalRun.case_results))
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lượt eval này.")
    return EvalRunDetail(
        id=run.id,
        git_commit_hash=run.git_commit_hash,
        model_version=run.model_version,
        dataset_version=run.dataset_version,
        total_cases=run.total_cases,
        errors=run.errors,
        category_accuracy=run.category_accuracy,
        avg_recall_at_k=run.avg_recall_at_k,
        avg_judge_score=run.avg_judge_score,
        judge_cases_scored=run.judge_cases_scored,
        created_at=run.created_at,
        cases=run.case_results,
    )
