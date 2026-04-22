from utils import LOGGER, uart_manager
import time

i = 0
while True:
    uart_manager.send_string(f"d:test,{i},{i},{i}")
    # LOGGER.info(f"test: {i}")
    i += 1
    time.sleep(1)
