"""Tải đúng phiên bản thư viện giao diện để ứng dụng chạy không phụ thuộc CDN."""
from pathlib import Path
from urllib.request import urlopen

root = Path(__file__).resolve().parent.parent / "qlcv" / "static" / "vendor"
root.mkdir(parents=True, exist_ok=True)
assets = {
    "bootstrap.min.css": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css",
    "bootstrap.bundle.min.js": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js",
    "chart.umd.min.js": "https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js",
}
for name, url in assets.items():
    with urlopen(url, timeout=45) as response:
        content = response.read()
    (root / name).write_bytes(content)
    print(f"Đã lưu {name}: {len(content)} byte.")
