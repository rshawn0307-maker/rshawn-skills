# 引擎安全机制（shared-engine-safety）

> **产线切换注（2026-11-20）：引擎归档。** 本文件所述 docx 引擎 `fill_answer_post.py` 已随产线切换归档保留、不再执行；**现行产线为 skill 内 `scripts/render_answer_cards.py`**（PIL 直出 6 张 1080×1440 PNG + 笔记文案.md；期号读 `图片输出/progress_answer.json`，字体/logo 缺失 STOP，只折行不截断、超高降档仍超高 FAIL，渲染 + logo 校验全过才追加 done）。以下内容保留作归档参考与回溯。

答一道 docx 引擎 skill 内 `scripts/fill_answer_post.py`（TR1 自 structured-post 引擎 v2 原样移植；旧技巧线引擎 fill_tips_post.py 已随技巧线退役删除，其 v3.0 安全模式记载随 git 历史可找回）。

## 引擎安全机制（fill_answer_post.py 实装口径）

1. **项目根解析**：`--project-root` > 环境变量 `ANSWER_PROJECT_ROOT` > 报错 exit 1（移植时取消旧 `__file__` 相对路径 fallback——引擎收 skill 内后相对解析指向 skill 目录非 vault，保留会误写 skill 目录）。
2. **写入前段数预检**：模板段数 ≠ 19 直接 exit 1（"请勿强行写入"），模板未动。
3. **快照先行**：每次运行前自动快照当前模板到 vault `scripts/_snapshots/`（最多 10 个，超出按修改时间倒序清理）——任何失败都可用最新快照回退。
4. **写入只改文本**：找第一个纯文本 run（有 w:t 无 drawing）写入，图片 run 完全不动；封面文本框双镜像（drawing 镜像 + VML fallback）同步写入。
5. **版式锁定**：段[9] 正文首段强制 pageBreakBefore，大纲区（段 2-8）分页符清除。
6. **写入后自动验证**：段数 19 / w:drawing 5 / 引流段样式（居中+加粗+#85120F）/ 封面双镜像前缀 / 分页符版式，任一不符 exit 1 且 `[KEEP] pending_answer.json 保留` 便于排查。
7. **退出码契约**：0=成功（pending 清理）；1=环境或验证失败（pending 缺失 / 模板缺失 / 段数预检失败 / 缺 question / 真题前缀违规 / 写入后验证不过）。缺大纲字段按源版本语义抛 KeyError 退出 1（原样保留，不另设码）。
8. **真题封面前缀铁律**：source 含真题类标记而 title_prefix 非「结构化历年考题：」直接 exit 1，防静默用错封面。
9. **引擎归属统一**：引擎收 skill 内 `scripts/`；项目根只留数据/模板/pending/快照；项目根遗留 `fill_structured_post.py` 已废弃勿用。
10. **失败回退**：验证失败不回滚字节（源版本口径：快照已留存写入前版本），从 `_snapshots/` 复制最新快照覆盖回模板路径即回退；pending 保留排查。

## 回归测试与沙箱纪律

- `scripts/test_fill_answer_post.py`：模板源用 skill 内 `assets/answer-template-baseline.docx`，全程只写系统临时目录副本；结束断言 vault 模板 1 与 baseline 的 sha256 前后不变；用例数低于下限即失败退出（不允许假绿）。
- 改引擎/模板/测试后必跑三套自测：`test_fill_answer_post.py` + `test_content_rules.py` + `test_check_prose.py`，全过才算交付。
- IMA 用例（如有）强制本地 fake stub，绝无真实网络调用、绝不创建真实笔记。
