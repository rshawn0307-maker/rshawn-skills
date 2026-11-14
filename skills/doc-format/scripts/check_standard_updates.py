#!/usr/bin/env python3
# 本脚本联网复查 skill 里登记过的国标是否仍是现行版本。
# 登记表就是本文件下面的 REGISTERED：改过标准结论后，它和 standards.md 两边要对上。
#
# 为什么需要它：
#   国标会换版、会废止。GB/T 7714 从 2015 换到 2025、GB/T 7713.1 从 2006 换到 2025，
#   都是真实发生过的。预设文件如果还写着旧版本，用户按它排版就会出错。
#   所以每隔一段时间（或用户提出异议时）要跑一次本脚本，把结论写进你自己那份 standards.md
#   （在用户数据目录里，skill 更新不会覆盖它；路径由脚本运行时打印）。
#
# 数据来源：全国标准信息公共服务平台（openstd.samr.gov.cn）的标准检索页。
#
# 用法：
#   python3 scripts/check_standard_updates.py            复查全部登记标准
#   python3 scripts/check_standard_updates.py --only "GB/T 9704"   只查一个
#   python3 scripts/check_standard_updates.py --offline   只打印登记表，不联网

import argparse   # 用于解析命令行参数
import html       # 用于还原 HTML 实体
import os         # 用于拼出 scripts 目录的绝对路径
import re         # 用于清洗 HTML 与匹配标准号
import ssl        # 用于在证书链异常时退化为不校验（只读公开数据，风险可控）
import subprocess # 用于调用 curl 抓取（本环境下 curl 的证书链是正常的）
import sys        # 用于控制退出码与错误输出
import urllib.parse    # 用于拼接检索 URL
import urllib.request  # 用于在 curl 不可用时兜底抓取

# 把 scripts 目录加入模块路径，保证能导入同目录下的公共库
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import spec_lib   # 导入公共库：用它算出「用户数据目录里那份 standards.md」的路径

# 本 skill 引用过的标准登记表。
# 字段：编号（不含年号与部分号）、本文件记录的完整版本、名称、类型、引用位置。
# 维护要求：每次复查后更新「本文件记录的完整版本」与文件顶部/预设里的核验日期。
REGISTERED = [
    {"number": "GB/T 9704",   "version": "GB/T 9704-2012",   "name": "党政机关公文格式",
     "kind": "国标", "used_in": "presets/gov-doc-cn.md、standards.md 第二节"},
    {"number": "GB/T 7713.1", "version": "GB/T 7713.1-2025", "name": "学位论文编写规则",
     "kind": "国标", "used_in": "presets/thesis-cn.md"},
    {"number": "GB/T 7713.2", "version": "GB/T 7713.2-2022", "name": "学术论文编写规则",
     "kind": "国标", "used_in": "presets/paper-cn.md"},
    {"number": "GB/T 7714",   "version": "GB/T 7714-2025",   "name": "信息与文献 参考文献著录规则",
     "kind": "国标", "used_in": "presets/paper-cn.md、presets/thesis-cn.md"},
    {"number": "GB/T 15834",  "version": "GB/T 15834-2011",  "name": "标点符号用法",
     "kind": "国标", "used_in": "standards.md 第五节、markdown-rules.md"},
    {"number": "GB/T 15835",  "version": "GB/T 15835-2011",  "name": "出版物上数字用法",
     "kind": "国标", "used_in": "standards.md 第五节、markdown-rules.md"},
    {"number": "GB 3100",     "version": "GB 3100-1993",     "name": "国际单位制及其应用",
     "kind": "国标", "used_in": "standards.md（公文中计量单位引用）"},
    {"number": "GB 3101",     "version": "GB 3101-1993",     "name": "有关量、单位和符号的一般原则",
     "kind": "国标", "used_in": "standards.md（公文中计量单位引用）"},
    {"number": "GB 3102",     "version": "GB 3102（所有部分）", "name": "量和单位",
     "kind": "国标", "used_in": "standards.md（公文中计量单位引用）"},
]

# 抓取网页：优先用 curl（本环境下证书链正常），失败时退回 urllib（不校验证书）
def fetch(url, timeout=25):
    try:                                                              # 先试 curl
        result = subprocess.run(                                      # 调用 curl
            ["curl", "-s", "-m", str(timeout), "-L",                   # 静默、限时、跟随跳转
             "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",   # 伪装浏览器 UA
             "-H", "Accept-Language: zh-CN,zh;q=0.9",                 # 声明中文优先
             url],                                                    # 目标地址
            capture_output=True, timeout=timeout + 10,                 # 捕获输出
        )
        if result.returncode == 0 and result.stdout:                   # 成功且有内容
            return result.stdout.decode("utf-8", "ignore"), "curl"      # 返回内容与来源
    except (FileNotFoundError, subprocess.TimeoutExpired):             # curl 不存在或超时
        pass                                                          # 继续走兜底
    try:                                                              # 兜底：urllib
        context = ssl.create_default_context()                         # 创建默认 SSL 上下文
        context.check_hostname = False                                 # 关闭主机名校验
        context.verify_mode = ssl.CERT_NONE                            # 关闭证书校验（只读公开数据）
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})   # 构造请求
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:   # 发起请求
            return response.read().decode("utf-8", "ignore"), "urllib"  # 返回内容与来源
    except Exception as error:                                         # 兜底也失败
        return None, f"失败：{error}"                                    # 返回空与错误说明

# 把 HTML 清洗成便于逐行匹配的纯文本行
def html_to_lines(raw):
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)           # 去掉脚本与样式
    text = re.sub(r"(?s)<(tr|td|div|p|br|li)[^>]*>", "\n", text)       # 块级标签换成换行
    text = re.sub(r"(?s)<[^>]+>", " ", text)                           # 去掉剩余标签
    text = html.unescape(text)                                        # 还原实体
    text = re.sub(r"[ \t\u3000]+", " ", text)                          # 压缩行内空白
    return [line.strip() for line in text.split("\n") if line.strip()]  # 返回非空行列表

# 在检索结果里找出该标准号的条目，返回 (完整标准号, 名称, 状态, 发布, 实施) 或 None
def result_count(lines):
    for line in lines:                                                  # 遍历所有行
        match = re.search(r"共\s*(\d+)\s*条标准", line)                    # 匹配「共 N 条标准」
        if match:                                                       # 命中
            return int(match.group(1))                                  # 返回结果数
    return None                                                         # 没写就返回空

def table_start(lines):
    for index, line in enumerate(lines):                                # 遍历所有行
        if line.strip() == "标准号":                                     # 找到表头「标准号」
            return index                                                # 返回表头位置
    return 0                                                            # 找不到就从头开始

def find_standard(lines, number):
    # 检索结果里标准号可能带年号（GB/T 9704-2012），也可能不带（GB 3101），两种情况都要认
    total = result_count(lines)                                         # 先看检索到多少条
    if total == 0:                                                      # 一条都没有
        return None                                                     # 直接判定为「未收录」
    start = table_start(lines)                                          # 只在结果表格内查找
    lines = lines[start:]                                               # 截取表格区域
    bare = number.replace("GB ", "").replace("GB/T ", "").replace("GB/Z ", "")   # 取出数字部分
    pattern = re.compile(r"^GB(?:/T|/Z)?\s*" + re.escape(bare) + r"(?:\.\d+)?(?:-\d{4})?$")   # 允许年号可选
    for index, line in enumerate(lines):                               # 遍历所有行
        if pattern.match(line.replace(" ", " ")):                       # 命中标准号行
            window = lines[index:index + 12]                            # 取其后 12 行作为字段区
            full = line.strip()                                        # 完整标准号
            if not re.search(r"-\d{4}$", full):                         # 结果里没带年号
                for candidate in window + lines[max(0, index - 3):index]:   # 在邻近行里找带年号的写法
                    match = re.search(r"GB(?:/T|/Z)?\s*" + re.escape(bare) + r"(?:\.\d+)?-\d{4}", candidate)   # 匹配带年号写法
                    if match:                                          # 找到
                        full = match.group(0)                          # 用带年号的写法作为完整标准号
                        break                                          # 跳出
            # 表格列不固定（语种、是否采标两列有时缺失），不能按固定下标取值，只能按「像什么」判断
            filler = {"EN", "中文", "是", "否", "—", "-", "×", "查看详细", "详情"}   # 这些是列占位值，不是标准名称
            name = ""                                                  # 标准名称
            state = ""                                                 # 状态
            publish = ""                                               # 发布日期
            implement = ""                                             # 实施日期
            for item in window:                                        # 遍历字段区
                text = item.strip()                                    # 去空白
                if not name and text not in filler and not re.fullmatch(r"\d+", text) \
                        and not re.search(r"\d{4}-\d{2}-\d{2}", text) \
                        and not re.search(r"现行|废止|即将实施|作废", text) \
                        and not re.match(r"^GB(?:/T|/Z)?\s*\d", text) \
                        and re.search(r"[\u4e00-\u9fffA-Za-z]", text) and len(text) > 2:   # 像名称的行（排除标准号本身）
                    name = text                                        # 记录名称
                    continue                                           # 继续
                if not state and re.search(r"现行|废止|即将实施|作废", text):   # 状态关键词
                    state = text                                       # 记录状态
                for date in re.findall(r"\d{4}-\d{2}-\d{2}", text):      # 找日期
                    if not publish:                                    # 第一个日期是发布
                        publish = date                                  # 记录发布
                    elif not implement:                                # 第二个是实施
                        implement = date                                # 记录实施
            return full, name, state, publish, implement                # 返回解析结果
    return None                                                        # 没找到

# 复查单个标准
def check_one(item, offline):
    print("=" * 66)                                                     # 打印分隔线
    print(f"【{item['number']}】{item['name']}")                          # 打印标准信息
    print(f"  本文件记录：{item['version']}")                             # 打印记录的版本
    print(f"  引用位置：{item['used_in']}")                               # 打印引用位置
    if offline:                                                        # 离线模式
        print("  （离线模式，未联网复查）")                                 # 打印说明
        return "skip"                                                  # 返回跳过
    url = ("https://openstd.samr.gov.cn/bzgk/gb/std_list"
           "?p.p1=0&p.p90=circulation_date&p.p91=desc&pageSize=50&p.p2=" + urllib.parse.quote(item["number"]))   # 拼接检索 URL，一次取 50 条避免漏结果
    raw, source = fetch(url)                                           # 抓取
    if raw is None:                                                    # 抓取失败
        print(f"  联网复查失败：{source}")                                 # 打印错误
        print("  → 请手工访问 https://openstd.samr.gov.cn/bzgk/gb/std_list 复核，不要凭印象下结论。")
        return "unknown"                                               # 返回未知
    found = find_standard(html_to_lines(raw), item["number"])           # 解析结果
    if not found:                                                      # 没找到
        print(f"  没有在检索结果里找到该标准号（数据来源：{source}）。")        # 打印提示
        print("  → 可能是标准号写法不同，或该标准不在公开系统里，请人工复核。")    # 提示
        return "unknown"                                               # 返回未知
    full, name, state, publish, implement = found                       # 拆解结果
    print(f"  平台返回：{full}　{name}")                                  # 打印平台数据
    print(f"  状态：{state or '（未解析到）'}　发布：{publish or '—'}　实施：{implement or '—'}")   # 打印状态与日期
    recorded_year = re.search(r"(\d{4})$", item["version"])             # 取本文件记录的年号
    found_year = re.search(r"(\d{4})$", full)                           # 取平台返回的年号
    if "废止" in state or "作废" in state:                               # 已废止
        print("  ❌ 该标准已废止，必须寻找替代标准并更新本 skill 的全部引用。")   # 打印严重问题
        return "obsolete"                                              # 返回废止
    if recorded_year and found_year and recorded_year.group(1) != found_year.group(1):   # 年号不一致
        print(f"  ⚠️ 平台上是 {found_year.group(1)} 版，本文件记录的是 {recorded_year.group(1)} 版，"
              f"需要确认是否换版并更新引用。")                              # 打印换版提醒
        return "changed"                                               # 返回变化
    print("  ✅ 与本文件记录一致，未发现换版迹象。")                          # 打印一致
    return "ok"                                                        # 返回正常

# 脚本入口
def main():
    parser = argparse.ArgumentParser(description="联网复查国标现行性")        # 构造解析器
    parser.add_argument("--only", help="只复查某个标准号，如 'GB/T 9704'")     # 单查参数
    parser.add_argument("--offline", action="store_true", help="只打印登记表，不联网")   # 离线开关
    args = parser.parse_args()                                          # 解析参数
    targets = REGISTERED                                               # 默认全部
    if args.only:                                                       # 指定了单个标准
        targets = [item for item in REGISTERED if args.only.replace(" ", "") in item["number"].replace(" ", "")]   # 过滤
        if not targets:                                                 # 没匹配到
            print(f"登记表里没有「{args.only}」。请先把它加入 REGISTERED 再复查。", file=sys.stderr)   # 提示
            return 2                                                    # 返回错误码
    print(f"复查 {len(targets)} 个标准，数据来源：全国标准信息公共服务平台 openstd.samr.gov.cn")   # 打印概况
    reminder = spec_lib.user_reference("standards.md")                 # 算「你自己那份 standards.md」的路径
    print(f"提醒：复查结论写进你自己那份 standards.md（{reminder}），并更新核对日期 verified_at。")   # 打印纪律
    print("     那份在用户数据目录里，skill 更新不会覆盖它。")            # 补充说明，避免用户写错地方
    print("     若发现出厂预设引用的标准过期了，那是 skill 本身要改的，把结论反馈给作者。")   # 区分「谁能改」
    results = {"ok": 0, "changed": 0, "obsolete": 0, "unknown": 0, "skip": 0}   # 初始化统计
    for item in targets:                                                # 逐个复查
        results[check_one(item, args.offline)] += 1                      # 累计结果
    print("=" * 66)                                                     # 打印分隔线
    print(f"汇总：一致 {results['ok']}，疑似换版 {results['changed']}，已废止 {results['obsolete']}，"
          f"未能确认 {results['unknown']}，跳过 {results['skip']}")        # 打印汇总
    if results["unknown"]:                                              # 有未确认项
        print("有标准未能联网确认。请人工访问官方平台复核，不要直接沿用旧结论。")   # 提示
    return 1 if (results["changed"] or results["obsolete"] or results["unknown"]) else 0   # 有问题返回非零

# 仅在直接运行时执行入口
if __name__ == "__main__":
    raise SystemExit(main())                                            # 用返回值作为退出码
