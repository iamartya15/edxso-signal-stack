"""Start Signal Stack:  python run.py   (http://127.0.0.1:5000)"""
import os

from signalstack import create_app
from signalstack.scheduler import start_scheduler

app = create_app()

if __name__ == "__main__":
    start_scheduler(app.config["DB_PATH"])
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
