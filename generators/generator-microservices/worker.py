#!/usr/bin/env python3
"""
Alias runner untuk log_generator.py di folder generator-microservices
Memungkinkan eksekusi dengan:
  python3 worker.py --mode <kondisi>
"""

import sys
from log_generator import main

if __name__ == "__main__":
    sys.exit(main())

