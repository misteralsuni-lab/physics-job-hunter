import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])
from src.scheduler.daily_run import start
start()
