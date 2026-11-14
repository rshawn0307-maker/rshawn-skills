#!/usr/bin/env python3
# 本脚本把 PDF / DOCX 渲染成 PNG 图片，用于「肉眼看一眼」确认排版真的对。
#
# 为什么必须有这一步：
#   实测发现本机的 LibreOfficeDev 看不到 macOS 系统字体，导出的 PDF 里中文会变成方框或空白，
#   但 PDF 里仍然能提取出正确的中文文本，所以纯文本检查完全查不出来。
#   唯一可靠的确认方式就是把页面渲染成图片，用眼睛看。
#
# 本脚本除了渲染，还会逐页报告「这一页的中文用了什么字体」，
#   方便直接定位到出问题的那一页，而不是只得到一句「整体有问题」。
#
# 用法：
#   python3 scripts/render_preview.py --pdf book.pdf --outdir preview/
#   python3 scripts/render_preview.py --docx book.docx --outdir preview/ --pages 1-3
#   python3 scripts/render_preview.py --pdf book.pdf --outdir preview/ --dpi 150
#   python3 scripts/render_preview.py --clean --outdir preview/     ← 看完必须跑这一条
#
# 【看完即删】渲染出来的 PNG 是核对用的临时产物，不是交付物。
#   目标是「不看图不算交付」，核对完就把图删掉，别留在用户的目录里积着。
#   图片目录里还有一个 _tmp/ 子目录（--docx 时转出的中间 PDF），--clean 会一并清掉。

import argparse   # 用于解析命令行参数
import os         # 用于路径处理
import shutil     # 用于整目录删除（--clean）
import subprocess # 用于调用 build_pdf 把 DOCX 转成 PDF
import sys        # 用于控制退出码与错误输出

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # 把 scripts 目录加入模块路径

import spec_lib   # 导入公共库（中文字体名判定等）

# 解析 "1-3,5" 这样的页码范围，返回页码集合（页码从 1 开始）
def parse_pages(spec, total):
    if not spec:                                                 # 未指定则全部
        return set(range(1, total + 1))                          # 返回全部页码
    pages = set()                                                # 初始化集合
    for part in spec.split(","):                                 # 按逗号拆分
        part = part.strip()                                      # 去空白
        if not part:                                             # 空片段
            continue                                             # 跳过
        if "-" in part:                                          # 区间
            start, end = part.split("-", 1)                      # 拆成两端
            for number in range(int(start), int(end) + 1):       # 遍历区间
                if 1 <= number <= total:                         # 在合法范围内
                    pages.add(number)                            # 收集
        elif part.isdigit():                                     # 单页
            number = int(part)                                   # 转成整数
            if 1 <= number <= total:                             # 在合法范围内
                pages.add(number)                                # 收集
    return pages or set(range(1, total + 1))                     # 解析失败时退回全部

# 统计某一页用了哪些字体渲染中文，以及是否存在「有中文但没有中文字体」的危险情况
def inspect_page_fonts(page):
    fonts = set()                                                # 收集该页所有字体名
    cjk_chars = 0                                                # 统计中文与中文标点字符数
    cjk_font_chars = 0                                           # 统计用中文字体渲染的中文字符数
    try:                                                         # 文本字典解析可能失败
        payload = page.get_text("dict")                          # 取结构化文本
    except Exception:                                            # 解析失败
        return fonts, 0, 0                                       # 返回空结果
    for block in payload.get("blocks", []):                      # 遍历文本块
        for line in block.get("lines", []):                      # 遍历行
            for span in line.get("spans", []):                   # 遍历 span
                text = span.get("text", "")                      # 取文本
                font = span.get("font", "")                      # 取字体名
                fonts.add(font)                                  # 收集字体名
                for ch in text:                                  # 逐字符判断
                    if "\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f" or "\uff00" <= ch <= "\uffef":   # 汉字或中文标点
                        cjk_chars += 1                           # 中文计数加一
                        if spec_lib.looks_like_cjk_font(font):   # 该 span 用的是中文字体（判定规则收在公共库）
                            cjk_font_chars += 1                   # 中文字体计数加一
    return fonts, cjk_chars, cjk_font_chars                      # 返回统计结果

# 把 PDF 渲染成 PNG，并逐页报告字体情况
def render_pdf(pdf_path, outdir, dpi, pages_spec):
    try:                                                         # 依赖可能缺失
        import fitz                                              # PyMuPDF
    except ImportError:                                          # 缺失时
        print("缺少依赖 PyMuPDF，请运行：pip3 install pymupdf", file=sys.stderr)   # 提示安装
        return 2                                                 # 返回环境错误码
    os.makedirs(outdir, exist_ok=True)                           # 创建输出目录
    document = fitz.open(pdf_path)                               # 打开 PDF
    total = document.page_count                                  # 取总页数
    pages = parse_pages(pages_spec, total)                       # 解析要渲染的页码
    zoom = dpi / 72.0                                            # 计算缩放比例（PDF 以 72dpi 为基准）
    suspicious = []                                              # 记录可疑页
    print(f"PDF 共 {total} 页，渲染 {len(pages)} 页到 {outdir}（{dpi} dpi）")   # 打印概况
    for number in sorted(pages):                                 # 遍历页码
        page = document.load_page(number - 1)                    # 载入该页
        fonts, cjk_chars, cjk_font_chars = inspect_page_fonts(page)   # 检查字体
        matrix = fitz.Matrix(zoom, zoom)                         # 构造缩放矩阵
        pixmap = page.get_pixmap(matrix=matrix)                  # 渲染成位图
        target = os.path.join(outdir, f"page-{number:03d}.png")  # 目标文件名
        pixmap.save(target)                                      # 保存图片
        # 判定可疑：这一页有中文，但没有任何中文字体参与渲染
        flag = ""                                                # 初始化标记
        if cjk_chars >= 10 and cjk_font_chars == 0:              # 有中文却完全没用中文字体
            flag = "  ⚠️ 疑似中文未正常渲染（没有中文字体参与）"       # 标记可疑，并加入清单
            suspicious.append(number)                            # 记录页码
        print(f"  第 {number:>3} 页 -> {os.path.basename(target)}"
              f"　中文 {cjk_chars} 字，其中中文字体渲染 {cjk_font_chars} 字{flag}")   # 打印每页情况
        if fonts:                                                # 若解析到字体
            names = "、".join(sorted(f for f in fonts if f)[:6])   # 最多列出 6 个字体名
            print(f"          字体：{names}")                     # 打印字体
    print("-" * 66)                                              # 打印分隔线
    if suspicious:                                               # 有可疑页
        print(f"⚠️ 有 {len(suspicious)} 页疑似中文没有用中文字体渲染：{suspicious}")   # 打印页号
        print("   请立刻打开这些图片目视确认。若中文显示为方框或空白，说明生成环境缺中文字体，")
        print("   处理办法见 references/fonts.md 第七节（LibreOffice 字体目录）。")
        return 1                                                 # 返回非零表示需要人工介入
    print("没有发现「有中文但无中文字体」的页面。仍请打开图片目视确认一遍，字体检查不能替代肉眼。")
    return 0                                                     # 返回成功码

# 把 DOCX 先转成 PDF 再渲染
def render_docx(docx_path, outdir, dpi, pages_spec):
    temp_dir = os.path.join(outdir, "_tmp")                      # 中间产物目录
    os.makedirs(temp_dir, exist_ok=True)                         # 创建目录
    temp_pdf = os.path.join(temp_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")   # 中间 PDF 路径
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_pdf.py")   # 调用同目录的转换脚本
    result = subprocess.run([sys.executable, script, "--input", docx_path, "--output", temp_pdf], text=True)   # 执行转换
    if result.returncode != 0 or not os.path.exists(temp_pdf):    # 转换失败
        print("DOCX 转 PDF 失败，无法渲染预览。请先看 build_pdf.py 的输出。", file=sys.stderr)   # 提示
        return 1                                                 # 返回失败码
    return render_pdf(temp_pdf, outdir, dpi, pages_spec)         # 渲染中间 PDF

# 删掉渲染出来的预览图片目录（看完即删）。
# 为什么要做成脚本里的一条命令，而不是让使用者手打 rm -rf：
#   ① 手打的删除命令容易打错路径，整目录删除不容许打错；
#   ② 有些执行环境直接禁用 rm 系命令，脚本自己删反而更可靠；
#   ③ 渲染目录里除了 PNG 还有一个 _tmp/ 子目录（中间 PDF），只删 PNG 会留下垃圾。
def clean_preview(outdir):
    target = os.path.abspath(outdir)                             # 归一化成绝对路径，便于安全判断
    if not os.path.isdir(target):                                # 目录本来就不存在
        print(f"无需清理：{target} 不存在")                        # 如实说明
        return 0                                                 # 当作成功（幂等）
    # 安全闸门：整目录删除绝不能作用在根目录、家目录或当前工作目录上，
    # 否则一次手滑就会删掉用户的项目。命中任一条就拒绝执行。
    dangerous = {os.path.abspath(os.sep), os.path.expanduser("~"), os.getcwd()}   # 禁止删除的目标
    if target in dangerous:                                      # 命中禁区
        print(f"已拒绝：{target} 是根目录/家目录/当前目录，不在清理范围内", file=sys.stderr)   # 说明原因
        return 2                                                 # 返回错误码
    shutil.rmtree(target, ignore_errors=True)                    # 递归删除整个预览目录
    print(f"已清理预览目录：{target}")                              # 告知用户
    print("（预览图是核对用的临时产物，不属于交付物；下次核对再重新渲染即可）")   # 解释为什么删
    return 0                                                     # 返回成功码

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="把 PDF/DOCX 渲染成 PNG，用于目视核对排版")   # 构造解析器
    group = parser.add_mutually_exclusive_group(required=True)   # 三件事只能做一件
    group.add_argument("--pdf", help="输入的 PDF 路径")           # PDF 输入
    group.add_argument("--docx", help="输入的 DOCX 路径（会先转成 PDF）")   # DOCX 输入
    group.add_argument("--clean", action="store_true", help="删掉预览目录（核对完必须跑这一条）")   # 清理开关
    parser.add_argument("--outdir", required=True, help="输出图片目录；--clean 时是要删的目录")   # 输出目录
    parser.add_argument("--dpi", type=int, default=110, help="渲染分辨率，默认 110")   # 分辨率
    parser.add_argument("--pages", help="要渲染的页码范围，如 1-3,5；默认全部")   # 页码范围
    args = parser.parse_args()                                   # 解析参数
    if args.clean:                                               # 要求清理
        return clean_preview(args.outdir)                        # 删除预览目录后结束
    if args.pdf:                                                 # PDF 输入
        if not os.path.exists(args.pdf):                         # 文件不存在
            print(f"文件不存在：{args.pdf}", file=sys.stderr)      # 打印错误
            return 2                                             # 返回错误码
        return render_pdf(args.pdf, args.outdir, args.dpi, args.pages)   # 渲染
    if not os.path.exists(args.docx):                            # DOCX 不存在
        print(f"文件不存在：{args.docx}", file=sys.stderr)          # 打印错误
        return 2                                                 # 返回错误码
    return render_docx(args.docx, args.outdir, args.dpi, args.pages)   # 渲染

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                     # 用返回值作为退出码
