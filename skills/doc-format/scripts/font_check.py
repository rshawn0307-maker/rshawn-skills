#!/usr/bin/env python3
# 本脚本检查字体可用性，并在字体缺失时给出「装上它，或由用户从本机已有的字体里指定」两条路。
#
# 字体清单怎么来的（重要）：
#   **首次使用时做一次全盘检测，之后一律读字体记忆，不再重新扫描。**
#   记忆文件在 ~/.cache/doc-format/font-memory.json，存了中文字体、全部字体与检测日期。
#   用户中途装上的字体不必重扫全盘，用 --remember 记一笔即可，下次就认为它已存在。
#   只有加 --refresh 才会重新全盘检测。
#
# 为什么这样设计：全盘扫描要 1 秒以上，而 spec_check / build_docx / verify_output
#   是三个独立进程，每个都扫一遍就是白烧；更糟的是老设计用「字体目录 mtime」判缓存失效，
#   用户装一个字体就必然触发重扫。
#
# 对每个缺失字体，脚本回答三个问题（只给答案，不替用户做选择）：
#     1. 这个字体能不能免费、合法地下载到？
#   2. 能 → 官方下载地址是什么？
#   3. 本机有哪些同类字体可以作为「用户可指定的候选」？
#
# 用法：
#   python3 scripts/font_check.py --list                     列出本机中文字体（走记忆）
#   python3 scripts/font_check.py --refresh                  强制重新全盘检测并刷新记忆
#   python3 scripts/font_check.py --remember 仿宋_GB2312       记住「这个字体已经装上了」
#   python3 scripts/font_check.py --forget 仿宋_GB2312         从记忆里移除某个字体
#   python3 scripts/font_check.py --guide 仿宋_GB2312          查询某个字体的获取指南
#   python3 scripts/font_check.py --has "PingFang SC"          只查询某个字体本机是否有
#   python3 scripts/font_check.py --suggest 宋体               缺字体时，列出本机可改用的同类字体
#   python3 scripts/font_check.py --spec build/x.spec.yaml     体检一份规格卡要用的字体是否齐全

import argparse   # 用于解析命令行参数
import os         # 用于把项目目录加入模块搜索路径
import sys        # 用于控制退出码

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # 把 scripts 目录加入模块路径
import spec_lib   # 导入本项目的公共库

# 打印环境信息：操作系统、用了哪些检测后端、各后端状态
def print_environment():
    print(f"操作系统：{spec_lib.detect_platform()}")                              # 打印平台
    print(f"扫描目录：{', '.join(spec_lib.font_search_dirs()) or '（未找到字体目录）'}")   # 打印扫描的目录
    info = spec_lib.font_memory_info()                                           # 取字体记忆概况
    print(f"字体清单来源：{info['来源']}")                                          # 说明这次用的是记忆还是首次检测
    if info["用户新增"]:                                                          # 有用户中途装上的字体
        print(f"  其中用户中途安装：{'、'.join(info['用户新增'])}")                    # 一并列出
    print("检测后端：")                                                          # 打印后端标题
    for name, status in spec_lib.font_detection_report().items():                # 遍历后端状态
        print(f"  - {name}：{status}")                                           # 打印每个后端的状态

# 打印本机所有可用的中文字体，按名称排序
def print_font_list():
    families = sorted(spec_lib.list_cjk_fonts())                                # 枚举并排序字体族名
    print_environment()                                                         # 先打印环境信息
    print("-" * 66)                                                             # 打印分隔线
    print(f"本机中文字体共 {len(families)} 个：")                                # 打印总数
    for name in families:                                                       # 逐个打印字体名
        print("  ", name)                                                       # 行首缩进两格

# 按字体名的类别挑「该查哪个字体池」。
# 本项目踩过的坑：早期 --has / --suggest / --guide 一律只查中文字体清单，
# 于是任何西文字体（Times New Roman、Courier New…）都会被误报成「本机没有」，
# 用户据此去装一个本来就有的字体，或者白白改掉规格。
# 判定规则与 spec_lib.missing_fonts 保持一致：含中文的查中文字体池，其余查全部字体池。
def pool_for(name):
    if spec_lib.is_cjk(name):                                                   # 字体名里含中文
        return spec_lib.list_cjk_fonts(), "中文字体"                               # 查中文字体清单
    return spec_lib.list_all_fonts(), "全部字体"                                  # 否则查全部字体清单

# 打印本机全部字体族（含西文）。
# 为什么要有它：--list 只列中文字体，但规格卡里还有西文槽位（Times New Roman 等），
# 早先没地方查西文，用户只能靠猜；--has 又因为只查中文池而误报，两头堵。
def print_font_list_all():
    families = sorted(spec_lib.list_all_fonts())                                # 枚举并排序全部字体族名
    print_environment()                                                         # 先打印环境信息
    print("-" * 66)                                                             # 打印分隔线
    print(f"本机全部字体共 {len(families)} 个（含西文）：")                        # 打印总数
    for name in families:                                                       # 逐个打印字体名
        print("  ", name)                                                       # 行首缩进两格

# 查询单个字体的获取指南，并顺带报告本机是否已有
def print_guide(name):
    available, pool_label = pool_for(name)                                      # 按字体类别挑字体池
    print(f"本机是否已有「{name}」：{'有' if spec_lib.font_is_available(name, available) else '没有'}")   # 打印检查结果
    print(f"（比对基准：本机{pool_label} {len(available)} 个）")                   # 说明这次是拿哪个清单比的
    print("-" * 66)                                                             # 打印分隔线
    print(spec_lib.font_acquisition_advice(name))                               # 打印获取决策树
    return 0                                                                    # 查询不是错误，返回成功

# 只回答「本机有没有这个字体」，方便规格体检里做单点判断
def check_has(names):
    missing = []                                                                # 初始化缺失列表
    for name in names:                                                          # 遍历待查字体
        available, pool_label = pool_for(name)                                  # 每个字体按自己的类别选池
        ok = spec_lib.font_is_available(name, available)                        # 判断是否存在
        print(f"{'有  ' if ok else '没有'} {name}（比对基准：{pool_label} {len(available)} 个）")   # 打印结果与比对基准
        if not ok:                                                              # 若缺失
            missing.append(name)                                                # 记入缺失列表
    return 1 if missing else 0                                                  # 有缺失返回非零退出码

# 缺字体时，列出本机可改用的同类字体，供用户从中指定一个。
# 这是「不要替身」规则的关键一环：脚本只给候选清单，选谁由用户定，选完写进规格卡的 resolved 字段。
def print_suggest(name):
    available, pool_label = pool_for(name)                                      # 按字体类别挑字体池
    if spec_lib.font_is_available(name, available):                             # 本机已经有这个字体
        print(f"本机已经有「{name}」，不需要替代，也不需要写 resolved。")             # 直接告知
        return 0                                                                # 返回成功
    print(f"本机没有「{name}」。两条路：")                                        # 说明前提
    print("  A. 装上它——" + spec_lib.font_acquisition_advice(name).split("\n")[1].strip())   # 复用获取指南的第二行
    suggestions = spec_lib.suggest_replacements(name, available)                # 计算同类候选
    if suggestions:                                                             # 有候选项
        print(f"  B. 改用本机已有的（把选中的写进规格卡 resolved 字段），同类候选 {len(suggestions)} 个：")   # 提示
        for item in suggestions:                                                # 逐个打印
            print(f"     {item}")                                                # 打印候选名
    else:                                                                       # 跨字体表里没有对应候选
        print("  B. 跨字体推荐表里没有与它同类的本机字体。")                          # 说明情况
    # 清单入口按类别给对：西文字体不在 --list（它只列中文字体）里，别把用户引到错的命令上
    if pool_label == "中文字体":                                                  # 查的是中文字体
        print(f"   本机{pool_label}共 {len(available)} 个，完整清单见 font_check.py --list")   # 指向中文清单
    else:                                                                       # 查的是西文/全部字体
        print(f"   本机{pool_label}共 {len(available)} 个，完整清单见 font_check.py --list-all")   # 指向全部清单
    return 0                                                                    # 返回成功

# 体检一份规格卡：把其中所有字体槽位与本机实际字体比对，缺任何一个都算不通过
def check_spec(spec_path):
    spec = spec_lib.load_spec(spec_path)                                        # 读取规格卡
    rows = spec_lib.collect_required_fonts(spec)                                # 取出全部字体槽位
    if not rows:                                                                # 一个字体槽位都没有
        print("规格卡里没有找到任何字体配置。")                                     # 提示
        return 0                                                                # 不算错误
    available = spec_lib.list_cjk_fonts()                                       # 枚举本机中文字体
    all_fonts = spec_lib.list_all_fonts()                                       # 枚举全部字体（含西文）
    print(f"规格卡：{spec_path}")                                                # 打印规格卡路径
    print(f"字体槽位 {len(rows)} 个：")                                           # 打印槽位数量
    missing = 0                                                                 # 缺失计数
    for use, required, actual, is_cjk_font in rows:                             # 逐槽位核对
        pool = available if is_cjk_font else all_fonts                          # 中文查中文字体池，西文查全部
        if not pool and not is_cjk_font:                                        # 西文且本机枚举不到清单
            print(f"  ?  {use}：{actual}（本机无法枚举西文字体，未能验证）")           # 降级为无法验证
            continue                                                            # 继续下一项
        ok = spec_lib.font_is_available(actual, pool)                           # 判断是否真的装了
        mark = "OK " if ok else "缺失"                                           # 打印用的标记
        arrow = f"（规格要求 {required}）" if actual != required else ""            # 替代时补上原字体
        print(f"  {mark} {use}：{actual}{arrow}")                                # 打印结果
        if not ok:                                                              # 计数缺失
            missing += 1                                                        # 累加
    if missing:                                                                 # 有缺失
        print("")
        print(spec_lib.font_block_message(spec, available))                     # 打印完整的缺字体说明与两条路
        return 4                                                                # 用退出码 4 表示「字体缺失」
    print("全部字体本机都有，可以生成。")                                          # 全部通过
    return 0                                                                    # 返回成功

# 强制重新全盘检测并刷新字体记忆
def refresh_memory():
    print("正在重新全盘检测本机字体（约 1 秒）…")                                  # 提示耗时
    spec_lib.list_cjk_fonts(force=True)                                          # 强制刷新，忽略记忆
    info = spec_lib.font_memory_info()                                           # 取刷新后的概况
    print(f"已刷新字体记忆：中文字体 {info['中文字体数']} 个，全部字体 {info['全部字体数']} 个。")   # 打印结果
    print("记忆文件：" + spec_lib.font_memory_path())                             # 打印记忆文件位置
    return 0                                                                     # 返回成功

# 记住「某个字体已经装上了」。用户中途安装字体后调用，避免为它重扫全盘。
def remember(name, kind):
    ok = spec_lib.remember_font(name, kind=kind, note="由 font_check --remember 记录")   # 写入记忆
    if not ok:                                                                   # 写入失败
        print(f"未能把「{name}」写进字体记忆，请检查记忆文件是否可写。", file=sys.stderr)   # 提示失败
        return 1                                                                 # 返回失败码
    print(f"已记住：「{name}」（{kind}）。以后不再为它重新检测。")                    # 提示成功
    print("记忆文件：" + spec_lib.font_memory_path())                             # 打印记忆文件位置
    return 0                                                                     # 返回成功

# 从字体记忆里移除某个字体（记错了，或用户把字体卸载了）
def forget(name):
    if not spec_lib.forget_font(name):                                           # 移除失败
        print(f"字体记忆里没有「{name}」，无需移除。")                              # 提示
        return 0                                                                 # 不算错误
    print(f"已从字体记忆里移除「{name}」。")                                        # 提示成功
    return 0                                                                     # 返回成功

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="检查中文字体可用性并给出获取指南")   # 构造参数解析器
    parser.add_argument("--list", action="store_true", help="列出本机所有中文字体")   # 列字体开关
    parser.add_argument("--list-all", action="store_true", help="列出本机全部字体（含西文）")   # 列全部字体开关
    parser.add_argument("--guide", help="查询某个字体的获取指南")                   # 获取指南参数
    parser.add_argument("--has", nargs="+", help="查询一个或多个字体本机是否存在")     # 存在性查询参数
    parser.add_argument("--suggest", help="缺字体时列出本机可改用的同类字体")          # 候选清单参数
    parser.add_argument("--spec", help="体检一份规格卡：它的字体本机是否齐全")          # 规格卡体检参数
    parser.add_argument("--refresh", action="store_true", help="强制重新全盘检测并刷新字体记忆")   # 刷新参数
    parser.add_argument("--remember", help="记住某个字体已安装，之后不再重新检测")      # 记忆参数
    parser.add_argument("--forget", help="从字体记忆中移除某个字体")                  # 移除参数
    parser.add_argument("--kind", default="cjk", choices=["cjk", "latin"], help="配合 --remember 使用：字体类别")   # 类别参数
    args = parser.parse_args()                                                 # 解析参数
    if args.list:                                                              # 若要求列字体
        print_font_list()                                                      # 执行列字体
        return 0                                                               # 正常退出
    if args.list_all:                                                          # 若要求列全部字体
        print_font_list_all()                                                  # 执行列全部字体
        return 0                                                               # 正常退出
    if args.guide:                                                             # 若查询获取指南
        return print_guide(args.guide)                                         # 打印指南
    if args.has:                                                               # 若查询存在性
        return check_has(args.has)                                             # 执行查询
    if args.suggest:                                                           # 若要求给候选清单
        return print_suggest(args.suggest)                                     # 打印候选
    if args.spec:                                                              # 若要求体检规格卡
        return check_spec(args.spec)                                           # 执行体检
    if args.refresh:                                                           # 若要求刷新记忆
        return refresh_memory()                                                # 执行刷新
    if args.remember:                                                          # 若要求记住某个字体
        return remember(args.remember, args.kind)                              # 写入记忆
    if args.forget:                                                            # 若要求移除某个字体
        return forget(args.forget)                                             # 从记忆移除
    parser.print_help()                                                        # 都没提供时打印帮助
    return 2                                                                   # 返回用法错误码

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                                   # 用返回值作为退出码
