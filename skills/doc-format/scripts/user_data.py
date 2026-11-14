#!/usr/bin/env python3
# 本脚本回答一个问题：用户自己产生的东西，该写到哪个文件？
#
# 为什么需要它：这个 skill 是两层结构 —— skill 目录里放「出厂规则」（随更新整体替换），
# 用户数据放用户自己的目录（更新碰不到）。两层文件同名，靠得很近，很容易写错地方：
# 一旦把用户的东西写进 skill 目录，下次 pull 就被覆盖了。
# 所以路径不给助手和用户手写，一律问这个脚本要 —— 它是唯一的、确定性的出处。
#
# 用法：
#   python3 scripts/user_data.py                 总览：目录在哪、哪些文件已经有了
#   python3 scripts/user_data.py --dir           打印用户数据目录（不存在就创建）
#   python3 scripts/user_data.py --path <名字>   打印某个用户层文件的路径（父目录一并创建）
#   例：python3 scripts/user_data.py --path known-issues.md
#       python3 scripts/user_data.py --path presets/我的报告格式.md

import argparse   # 用于解析命令行参数
import os         # 用于路径拼装与建目录
import sys        # 用于控制退出码

# 把 scripts 目录加入模块路径，保证能导入同目录下的公共库
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import spec_lib   # 导入本项目的公共库（两层结构的路径定义都在它里面）

# 用户会改写的那几份参考文件：文件名 → 这份文件是干什么的
USER_FILES = (
    ("known-issues.md", "你自己遇到的问题与处置记录"),      # 出问题、修好之后记这儿
    ("standards.md", "你自己核验或更正过的标准记录"),        # 查证了某个国标的最新状态就记这儿
    ("fonts.md", "你自己查到的字体授权与排字坑"),             # 查到某款字体的授权情况就记这儿
)

# 用几行话说清两层结构是怎么回事
def explain():
    print("这个 skill 的文件分两层，别写错地方：")                                  # 开场一句
    print(f"  出厂规则（只读）：{spec_lib.SKILL_ROOT}")                            # 出厂层路径
    print("      代码、内置预设、上面几份参考文件的出厂版本。更新 skill 时整体替换，改了会丢。")   # 说明
    print(f"  用户数据（可写）：{spec_lib.user_data_dir()}")                       # 用户层路径
    print("      你自己产生的一切。更新 skill 碰不到它，换台电脑记得带走。")            # 说明
    print("  读的时候两层都读，冲突以你那份为准；写的时候只写用户目录。")               # 核心规矩

# 总览：列出该目录在哪、每个文件现在是什么状态
def overview():
    explain()                                                                   # 先讲结构
    print()                                                                     # 空行
    target = spec_lib.user_data_dir()                                            # 用户数据目录
    if not os.path.isdir(target):                                                # 目录还没建
        print("用户数据目录还没建。第一次要用的时候会自动建，也可以现在就跑：")        # 说明
        print("  python3 scripts/user_data.py --dir")                             # 给出命令
        return 0                                                                # 正常结束
    print(f"用户数据目录：{target}")                                              # 再报一次路径
    for name, purpose in USER_FILES:                                             # 逐个看那几份参考文件
        path = spec_lib.user_reference(name)                                      # 用户层路径
        if os.path.exists(path):                                                  # 用户层已经有
            count = sum(1 for _ in open(path, encoding="utf-8", errors="ignore"))  # 数一下行数
            print(f"  {name:<20} 已有（{count} 行）—— {purpose}")                   # 报状态
        else:                                                                     # 用户层还没有
            print(f"  {name:<20} 还没建 —— {purpose}")                             # 报状态
    presets = spec_lib.user_preset_dir()                                          # 用户预设目录
    saved = []                                                                    # 已有预设文件名
    if os.path.isdir(presets):                                                    # 目录存在才数
        saved = [n for n in sorted(os.listdir(presets))                           # 列出文件
                 if n.endswith(".md") and not n.startswith("_")]                   # 只算预设
    print(f"  {'presets/':<20} {len(saved)} 个自存预设")                            # 报预设数量
    print()                                                                        # 空行
    print("要记东西时，先问这个脚本该写哪个文件：")                                    # 使用提示
    print("  python3 scripts/user_data.py --path known-issues.md")                  # 示例
    return 0                                                                        # 正常结束

# 入口
def main():
    parser = argparse.ArgumentParser(description="用户数据放哪：路径与现状")            # 构造参数解析器
    parser.add_argument("--dir", action="store_true", help="打印用户数据目录（不存在就创建）")   # 目录开关
    parser.add_argument("--path", metavar="名字", help="打印某个用户层文件的路径（如 known-issues.md）")   # 文件开关
    args = parser.parse_args()                                                      # 解析参数
    if args.path:                                                                   # 用户问了某个文件
        target = spec_lib.user_reference(args.path)                                  # 拼出用户层路径
        os.makedirs(os.path.dirname(target), exist_ok=True)                          # 父目录建好（presets/ 这种要支持）
        print(target)                                                               # 只打印路径，方便别的程序接
        return 0                                                                    # 正常结束
    if args.dir:                                                                    # 用户问了目录
        target = spec_lib.user_data_dir()                                           # 用户数据根目录
        os.makedirs(target, exist_ok=True)                                          # 建出来
        print(target)                                                               # 打印路径
        return 0                                                                    # 正常结束
    return overview()                                                               # 什么都没问就报总览

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                                        # 用返回值作为退出码
