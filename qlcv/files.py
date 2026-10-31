import re
import shutil
from pathlib import Path
from uuid import uuid4

from flask import current_app


def path_for(key):
    if not re.fullmatch(r"[a-f0-9]{32}", key):
        raise ValueError("Khóa lưu trữ không hợp lệ.")
    return Path(current_app.config["UPLOAD_FOLDER"]) / key


def store(upload):
    key = uuid4().hex
    path = path_for(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as dest:
            shutil.copyfileobj(upload.stream, dest)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return key, path.stat().st_size


def remove_after_commit(keys):
    # Chỉ dọn tệp sau COMMIT: khi giao dịch lỗi, tệp đang dùng vẫn nguyên vẹn.
    for key in keys:
        try:
            path_for(key).unlink(missing_ok=True)
        except (OSError, ValueError):
            current_app.logger.warning("Còn tệp cần dọn; chạy lệnh dọn tệp mồ côi trong README.")
