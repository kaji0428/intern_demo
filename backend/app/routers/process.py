from enum import Enum
from fastapi import APIRouter, UploadFile, File, Form

router = APIRouter()

class Action(str, Enum):
    sum = "sum"
    pie = "pie"
    ctr_top = "ctr_top"
    fix_encoding = "fix_encoding"
    split_1000 = "split_1000"
    merge = "merge"

@router.post("")
async def process(
    action: Action = Form(...),
    file: UploadFile | None = File(None),
    file2: UploadFile | None = File(None),
):
    return {"message": f"action={action}", "note": "logic TBD"}
