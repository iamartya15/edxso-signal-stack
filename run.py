"""Start Signal Stack:  python run.py   (http://127.0.0.1:5000)"""
from signalstack import create_app
from signalstack.scheduler import start_scheduler

app = create_app()

if __name__ == "__main__":
    start_scheduler(app.config["DB_PATH"])
    app.run(host="127.0.0.1", port=5000, debug=False)
