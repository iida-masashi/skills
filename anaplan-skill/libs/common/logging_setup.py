import logging
import sys
from pathlib import Path


def setup_logging(log_file: str | Path, level: int = logging.INFO, logger_name: str | None = None) -> logging.Logger:
    """ロギングの設定を行う（コンソールとファイルの両方に出力）"""
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    # ハンドラが重複して追加されるのを防ぐ
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # コンソール出力
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        # ファイル出力
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
