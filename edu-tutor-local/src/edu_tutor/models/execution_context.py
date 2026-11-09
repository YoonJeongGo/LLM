"""Explicit authenticated execution scope, carried into the existing job thread."""
from contextvars import ContextVar

execution_allowance = ContextVar("execution_allowance", default=None)
student_session = ContextVar("student_session", default=None)
requested_student_session = ContextVar("requested_student_session", default=None)


def bind_scope(payload):
    scope = execution_allowance.get()
    session_id = student_session.get()
    if requested_student_session.get() and requested_student_session.get() != session_id:
        from .budget import ResourceBudgetExceeded
        raise ResourceBudgetExceeded("학생 세션의 실제 대화·수업·사진 소속을 먼저 확인해야 합니다.")
    if session_id:
        if payload.get("student_session_id", session_id) != session_id:
            from .budget import ResourceBudgetExceeded
            raise ResourceBudgetExceeded("다른 학생 세션의 예산으로 실행할 수 없습니다.")
        payload = {**payload, "student_session_id": session_id}
    if scope and "execution_allowance_id" not in payload:
        return {**payload, "execution_allowance_id": scope}
    return payload
