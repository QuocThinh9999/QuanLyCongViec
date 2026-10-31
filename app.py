from qlcv import create_app

app = create_app()

if __name__ == "__main__":
    from waitress import serve

    print("Quản lý công việc: http://127.0.0.1:5000")
    serve(app, host="127.0.0.1", port=5000)
