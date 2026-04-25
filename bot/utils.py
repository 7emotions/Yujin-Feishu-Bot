import logging


class ColoredFormatter(logging.Formatter):
    # ANSI 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',     # 青色
        'INFO': '\033[32m',      # 绿色
        'WARNING': '\033[33m',   # 黄色
        'ERROR': '\033[31m',     # 红色
        'CRITICAL': '\033[35m',  # 紫色
    }
    RESET = '\033[0m'

    def format(self, record):
        # 根据级别获取颜色
        color = self.COLORS.get(record.levelname, self.RESET)
        # 原始格式化消息
        message = super().format(record)
        # 包裹颜色并重置
        return f"{color}{message}{self.RESET}"
