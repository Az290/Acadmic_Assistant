from pydantic import BaseModel, EmailStr, Field


class CreateCourseRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20, description="Mã lớp, vd: CS301-T7")
    name: str = Field(min_length=1, max_length=200, description="Tên lớp, vd: Nhập môn Lập trình - Lớp thứ 7")


class CoursePublic(BaseModel):
    id: int
    code: str
    name: str
    owner_id: int

    model_config = {"from_attributes": True}


class EnrollRequest(BaseModel):
    student_email: EmailStr


class EnrollmentPublic(BaseModel):
    user_id: int
    course_id: int
    role_in_course: str

    model_config = {"from_attributes": True}
