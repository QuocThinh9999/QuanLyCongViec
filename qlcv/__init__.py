from datetime import timezone, timedelta

from flask import Flask, g, render_template, request
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from .config import ROOT, settings
from .db import close_db, init_db
from .permissions import ROLES


def create_app(overrides=None):
    app = Flask(__name__, instance_path=str(ROOT / "instance"))
    app.config.update(settings())
    if overrides:
        app.config.update(overrides)
    init_db(app)
    CSRFProtect(app)
    app.teardown_appcontext(close_db)
    from .routes import bp
    app.register_blueprint(bp)

    @app.context_processor
    def context():
        return {"roles": ROLES, "current_user": g.get("user")}

    @app.template_filter("time_vn")
    def time_vn(value):
        return value.astimezone(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M") if value else "—"

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_template("error.html", code=400, message="Biểu mẫu đã hết hạn hoặc thiếu mã bảo vệ. Tải lại trang rồi thử lại."), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        messages = {400: "Thông tin gửi lên không hợp lệ.", 403: "Bạn không có quyền thực hiện thao tác này.",
                    404: "Không tìm thấy nội dung.", 405: "Phương thức truy cập không hợp lệ.",
                    413: "Tệp vượt quá giới hạn 25 MB.", 429: "Đăng nhập quá nhiều lần. Vui lòng thử lại sau."}
        return render_template("error.html", code=error.code, message=messages.get(error.code, "Không thể xử lý yêu cầu.")), error.code

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        # Không trả ngoại lệ, tham số truy vấn hoặc thông tin kết nối ra trình duyệt/log.
        close_db()
        return render_template("error.html", code=503, message="Chưa kết nối được cơ sở dữ liệu hoặc schema không phù hợp. Vui lòng kiểm tra cấu hình."), 503

    @app.errorhandler(500)
    def server_error(error):
        return render_template("error.html", code=500, message="Có lỗi khi xử lý. Dữ liệu chưa hoàn tất đã được hoàn tác."), 500

    return app
