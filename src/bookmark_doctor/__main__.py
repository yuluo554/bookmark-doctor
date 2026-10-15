"""``python -m bookmark_doctor`` 入口（薄模块，绝对导入）。"""

from bookmark_doctor.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
