#!/usr/bin/env python3
# 本脚本是「结构前置体检」：在任何生成动作之前，先回答一个问题 ——
# 这份稿子有没有结构？没有结构就先跟用户确认，别急着生成。
#
# 为什么必须放在最前面：
#   结构是骨架。骨架没定就套规格生成，标题会退化成正文段落，
#   产出的是一篇没有任何层次的文档；用户拿到的就是一份垃圾，还得推倒重来。
#   反复生成只会浪费时间和 token，正确做法是先问清结构，一次生成到位。
#
# 本脚本做什么：
#   · 读源稿（.md / .txt 直接读；.docx / .pdf 先抽成 Markdown）+ 若给了 --spec，则按规格卡出报告
#   · 统计标题层级、段落数、列表、引用、表格、篇幅
#   · 判定「结构可用 / 无结构 / 分段缺失 / 层级跳跃」，并列出该问用户的问题
#
# 本脚本不做什么：
#   · 不生成任何文件；不替用户拍板结构；不改措辞、不动标点。
#
# 退出码：
#   0  结构可用，可以直接进入规格确认与生成
#   5  必须先跟用户确认结构（无标题层级 / 只有一整段 / 层级跳跃），确认前不要生成

import argparse   # 用于解析命令行参数
import io         # 用于按 UTF-8 读写文件
import os         # 用于处理路径与判断文件是否存在
import sys        # 用于设置退出码与把错误写进 stderr

# 把 scripts 目录加入模块路径，保证能导入本项目自己的库
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import spec_lib   # 本项目公共库：块解析与结构体检判定都收在这里

# 读出源稿的 Markdown 文本：纯文本类直接读，Word / PDF 借 extract_source 抽成 Markdown。
# 这样无论用户丢来的是 md、txt 还是 Word，结构判定走的都是同一套规则。
def read_source(path):
    if not os.path.exists(path):                       # 文件不存在
        raise FileNotFoundError(f"文件不存在：{path}")     # 明确报错，不猜
    extension = os.path.splitext(path)[1].lower()      # 取小写扩展名
    if extension in (".md", ".markdown", ".txt", ".text"):   # 纯文本类
        return io.open(path, encoding="utf-8", errors="replace").read()   # 直接读全文
    import extract_source                              # 其余格式借抽取脚本（延迟导入，避免无谓依赖）
    markdown, _has_structure, _note = extract_source.extract(path)   # 抽取成 Markdown 文本
    return markdown                                    # 返回文本

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="结构前置体检：先确认结构，再谈生成")   # 构造参数解析器
    parser.add_argument("input", nargs="?", help="源文件路径（.md / .txt / .docx / .pdf）")   # 位置参数：源文件
    parser.add_argument("--text", help="直接给定文字（用户在对话里粘贴的内容）")   # 也可以直接给文字
    parser.add_argument("--spec", help="规格卡路径；给了它就把体裁与载体的要求一并核对")   # 可选的规格卡
    parser.add_argument("--quiet", action="store_true", help="只输出一行判定，供脚本串联调用")   # 精简输出开关
    args = parser.parse_args()                         # 解析参数

    if not args.input and not args.text:               # 既没给文件也没给文字
        print("请给出源文件路径，或用 --text 直接粘贴文字。", file=sys.stderr)   # 提示用法
        return 2                                       # 退出码 2 表示用法错误

    try:                                               # 读取源稿
        text = args.text if args.text else read_source(args.input)   # 有 --text 就用文字，否则读文件
    except (FileNotFoundError, ValueError) as error:   # 文件不存在或格式不支持
        print(str(error), file=sys.stderr)             # 把原因写进 stderr
        return 2                                       # 退出码 2 表示输入有问题

    blocks = spec_lib.parse_markdown_blocks(text)      # 用公共解析器切成块（结构判定只依赖块）
    report = spec_lib.source_structure_report(blocks)  # 做结构体检

    print(f"结构前置体检：{args.input or '（直接给定的文字）'}")   # 报告标题，写清来源
    print("=" * 60)                                    # 分隔线
    if args.quiet:                                     # 精简模式
        print(report["verdict"])                       # 只打一行判定
    else:                                              # 完整模式
        print(spec_lib.describe_structure(report))     # 打完整报告（统计 + 判定 + 待确认问题）
    if args.spec:                                      # 给了规格卡
        spec = spec_lib.load_spec(args.spec)           # 读规格卡
        carriers = ", ".join((spec.get("meta") or {}).get("carriers") or [])   # 取载体清单
        print(f"目标载体：{carriers or '（规格卡没写）'}")   # 告诉用户这份稿子准备出成什么

    if report["needs_confirmation"]:                   # 需要先跟用户确认结构
        print("-" * 60)                                # 分隔线
        print("⛔ 先不要生成。按下面顺序跟用户确认结构，确认后再进规格确认与生成：")   # 明确拦下
        print("   ① 把上面的判定与统计原样念给用户（标题几个、正文几段、多少字）")   # 第一步
        print("   ② 逐条问「待确认」里的问题，每条都给一个推荐值，别让用户凭空想")   # 第二步
        print("   ③ 用户点头后，或按推断结果、或按用户给的层级改稿，再生成文件")   # 第三步
        print("      确认过的标题必须写进稿子：infer_structure.py 加 --title（首块是文档标题），")   # 关键补充
        print("      否则标题仍是普通正文段，生成出来不居中、不套标题样式。")           # 说清后果
        print("      用户确认「就是不要标题」时，生成脚本加 --allow-flat 放行。")   # 逃生开关
        return 5                                       # 退出码 5 表示「结构未确认」

    print("-" * 60)                                    # 分隔线
    print("✅ 结构可用，可以进入规格确认与生成。")          # 结构没问题
    return 0                                           # 正常退出

if __name__ == "__main__":                             # 作为脚本直接运行时
    sys.exit(main())                                   # 用 main 的返回值当退出码
