import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import runpod
from handler import handler, wait_for_server

if __name__ == "__main__":
    wait_for_server()
    runpod.serverless.start({"handler": handler})
