class UnRelatedError(Exception):
    """无关错误"""

    pass


class UnKnowUnitError(Exception):
    """未知角色错误"""

    def __init__(self, unknown: str, name: str, score: int):
        self.unknown = unknown
        self.name = name
        self.score = score

    def __str__(self):
        if self.score >= 70:
            return f'无法识别"{self.unknown}"，系统猜测为"{self.name}"，相似度{self.score}%'
        else:
            return f'无法识别"{self.unknown}"'


class NotEnoughUnitError(Exception):
    """角色数量不足错误"""

    def __init__(self, need: int = 4):
        self.need = need

    def __str__(self):
        return f"角色数量不足，至少需要{self.need}个角色才能进行查询"


class TooManyUnitError(Exception):
    """角色数量过多错误"""

    def __init__(self, limit: int = 5):
        self.limit = limit

    def __str__(self):
        return f"角色数量过多，最多只能识别{self.limit}个角色进行查询"


class NotValidTeamError(Exception):
    """无效错误"""

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class AllNoResultError(Exception):
    """全部无结果错误"""

    def __init__(self):
        pass

    def __str__(self):
        return "所有查询均无结果"


class NoFreeCollisionError(Exception):
    """无冲配对失败错误"""

    def __init__(self):
        pass

    def __str__(self):
        return "无冲配对失败，无法找到合适的解法"
