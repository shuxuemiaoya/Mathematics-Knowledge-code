def infer_chapter(tit: str, qp: int, book_idx: int) -> tuple[str, str]:
    """Return (chapter_folder, cleaned_section_title) based on book page numbers."""
    tit = tit.strip()
    if book_idx == 1:
        # Book 1: 选修二
        # Chapter 4: P1-38
        # Chapter 5: P39-85
        # Comprehensive: P86+
        if qp is not None:
            if qp <= 38:
                return "01_第四章_数列", tit
            elif qp <= 85:
                return "02_第五章_一元函数的导数及其应用", tit
            else:
                return "03_综合专练与模块测试", tit
        return "01_第四章_数列", tit

    elif book_idx == 2:
        # Book 2: 必修一
        # Chapter 1: P1-20
        # Chapter 2: P21-36
        # Chapter 3: P37-64
        # Chapter 4: P65-100
        # Chapter 5: P101-140
        # Comprehensive: P141+
        if qp is not None:
            if qp <= 20:
                return "01_第一章_集合与常用逻辑用语", tit
            elif qp <= 36:
                return "02_第二章_一元二次函数_方程和不等式", tit
            elif qp <= 64:
                return "03_第三章_函数的概念与性质", tit
            elif qp <= 100:
                return "04_第四章_指数函数与对数函数", tit
            elif qp <= 140:
                return "05_第五章_三角函数", tit
            else:
                return "06_综合专练与模块测试", tit
        return "01_第一章_集合与常用逻辑用语", tit

    elif book_idx == 3:
        # Book 3: 选修一
        # Chapter 1: P1-28 (1.1 - 1.4, 专题1, 第一章素养检测, 第一章高考强化)
        # Chapter 2: P29-53 (2.1 - 2.5, 专题2-4, 第二章素养检测, 第二章高考强化)
        # Chapter 3: P54-91 (3.1 - 3.3, 专题5-9, 第三章素养检测, 第三章高考强化)
        # Comprehensive: P92+ (专练1, 专练2, 模块综合测试)
        if "1.3.1" in tit and "表示" in tit:
            tit = "1.3.1 空间直角坐标系与空间向量运算的坐标表示"
        elif "2.1.1" in tit and "判定" in tit:
            tit = "2.1.1 倾斜角与斜率及两条直线平行和垂直的判定"

        if qp is not None:
            if qp <= 28:
                return "01_第一章_空间向量与立体几何", tit
            elif qp <= 53:
                return "02_第二章_直线和圆的方程", tit
            elif qp <= 91:
                return "03_第三章_圆锥曲线的方程", tit
            else:
                return "04_综合专练与模块测试", tit
        return "01_第一章_空间向量与立体几何", tit

