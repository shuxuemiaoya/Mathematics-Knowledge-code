def infer_chapter_book2(tit: str, qp: int | None) -> tuple[str, str]:
    t = tit.strip()
    if "性质" in t and ("4.1" in t or "无理数" in t):
        t = "4.1.1 n次方根与分数指数幂及4.1.2 无理数指数幂及其运算性质"
    elif "4.4.1" in t:
        t = "4.4.1 对数函数的概念及4.4.2 对数函数的图象和性质"
    elif "5.6.1" in t:
        t = "5.6.1 匀速圆周运动的数学模型及5.6.2 函数 y = A sin(ωx + φ) 的图象"

    # Precise page thresholds based on book TOC:
    # 第一章 P1-19 (P20 is 2.1)
    # 第二章 P20-32 (P33 is 3.1)
    # 第三章 P33-61 (P62 is 4.1)
    # 第四章 P62-94 (P95 is 5.1)
    # 第五章 P95-140
    # 综合测试 P141+
    if qp is not None:
        if qp <= 19:
            return "01_第一章_集合与常用逻辑用语", t
        elif qp <= 32:
            return "02_第二章_一元二次函数_方程和不等式", t
        elif qp <= 61:
            return "03_第三章_函数的概念与性质", t
        elif qp <= 94:
            return "04_第四章_指数函数与对数函数", t
        elif qp <= 140:
            return "05_第五章_三角函数", t
        else:
            return "06_综合专练与模块测试", t
    return "01_第一章_集合与常用逻辑用语", t

