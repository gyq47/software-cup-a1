from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.services.diagnosis_service import confirm_alarm_diagnosis, diagnose_fault_image

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


class DiagnosisConfirmRequest(BaseModel):
    device_model: str | None = None
    mode: str | None = None
    level: str | None = None
    selected_alarm_codes: list[str] = []
    selected_alarm_texts: list[str] = []
    user_confirm_note: str | None = None
    fault_description: str | None = None
    vision_result: dict[str, Any] = {}


@router.post("/image")
async def diagnose_image(
    image: UploadFile = File(...),
    text: str | None = Form(default=None),
    device_model: str | None = Form(default=None),
    mode: str | None = Form(default=None),
    level: str | None = Form(default=None),
    alarm_code: str | None = Form(default=None),
) -> dict[str, Any]:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只允许上传图片文件")

    try:
        image_bytes = await image.read()
        result = diagnose_fault_image(
            image_bytes=image_bytes,
            content_type=image.content_type,
            text=text,
            device_model=device_model,
            mode=mode,
            level=level,
            alarm_code=alarm_code,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="多模态故障诊断失败") from exc

    return result


@router.post("/confirm")
def confirm_diagnosis(request: DiagnosisConfirmRequest) -> dict[str, Any]:
    if not request.selected_alarm_codes:
        raise HTTPException(status_code=400, detail="请至少选择一个报警候选")

    try:
        return confirm_alarm_diagnosis(
            device_model=request.device_model,
            mode=request.mode,
            level=request.level,
            selected_alarm_codes=request.selected_alarm_codes,
            selected_alarm_texts=request.selected_alarm_texts,
            user_confirm_note=request.user_confirm_note,
            fault_description=request.fault_description,
            vision_result=request.vision_result,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="确认报警诊断失败") from exc
