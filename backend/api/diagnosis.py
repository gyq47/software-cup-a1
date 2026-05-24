from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.services.diagnosis_service import diagnose_fault_image

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


@router.post("/image")
async def diagnose_image(
    image: UploadFile = File(...),
    text: str | None = Form(default=None),
    device_model: str | None = Form(default=None),
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
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="多模态故障诊断失败") from exc

    return result
