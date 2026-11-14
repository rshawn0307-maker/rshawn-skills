# 这个目录已经不用了（保留只为兼容旧版本）

用户自己保存的预设**不再写在这里**，改放在用户自己的目录：

```
~/.local/share/doc-format/presets/
```

## 为什么搬走

这个目录在 skill 内部。skill 目录是「代码 + 内置预设」，更新 skill 时会整体替换 ——
预设放在里面的话，用户更新一次就把自己攒的东西一起换掉了；
而且它会出现在 `git status` 里，一不小心就跟着提交进别人的仓库。

用户自己存的东西属于用户，不该住在代码目录里。字体记忆同理，放在
`~/.cache/doc-format/font-memory.json`（那是缓存，删了下次自动重建）。

## 旧预设怎么办

**不用管。** 脚本会自动把这里的 `.md` 预设搬到新位置，并打印一句说明：

- 跑 `python3 scripts/save_preset.py --list` 或存新预设时会自动搬；
- 新位置已有同名文件时**不会覆盖**，那份旧文件会留在原处由用户自己处理；
- 还没搬完之前，读取路径两边都认，不影响使用。

（以 `_` 开头的文件不会被当成预设，包括本文件。）

## 相关

- 整个用户数据根目录可以用环境变量 `DOC_FORMAT_HOME` 覆盖（测试与隔离用）；
  路径别手写，问脚本要：`python3 scripts/user_data.py --dir`。
- 用户数据目录里除了 `presets/`，还会有你自己记的 `known-issues.md`、`standards.md`、`fonts.md`
  —— 这些是「用户数据层」，与 skill 目录里的出厂版本读两份、冲突以你那份为准。
  跑 `python3 scripts/user_data.py` 可以看到现状。
- 规格参数含义见 `references/spec-schema.md`；预设总览见 `SKILL.md` 的「预设库」一节。
