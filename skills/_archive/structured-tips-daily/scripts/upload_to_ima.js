#!/usr/bin/env node
/**
 * upload_to_ima.js v2.1 -- 将「结构化答题技巧·每日一练」内容上传到 IMA 笔记并同步知识库
 *
 * 用法:
 *   node upload_to_ima.js "<md文件路径>" "<笔记标题>" [--fresh]
 *   --fresh 忽略历史状态强制新建笔记（默认幂等复用，重试绝不重复建笔记）
 *
 * 依赖:
 *   ima_api.cjs（默认 <skill>/../ima-skill/ima_api.cjs，可用环境变量 IMA_API_PATH 覆盖）
 *   依赖检查先于任何网络调用。
 *
 * 幂等设计（防重复建笔记）:
 *   状态文件: md 文件同目录 .ima_upload_state.json
 *   key: "<md绝对路径>|<笔记标题>"  value: {note_id, kb_done, updated_at}
 *   - 笔记创建成功后立即落盘状态（kb_done:false），之后任何一步失败，
 *     重试都会复用已存在的 note_id，绝不再调 import_doc。
 *   - 知识库同步成功后更新 kb_done:true；此后重试直接返回成功（零 API 调用）。
 *   - 状态读写失败仅告警，不阻断上传主流程。
 *
 * 退出码:
 *   0  笔记创建 + 知识库同步均成功（文件夹缺失时降级到库根目录仍算 0；幂等复用也算 0）
 *   1  用法错误 / md 文件不存在或不可读
 *   2  依赖缺失 / IMA 笔记创建失败
 *   3  笔记已创建，但知识库同步失败（部分成功，note_id 已给出，可安全重试）
 *
 * 输出契约:
 *   stdout 最后一行是结构化 JSON:
 *   {"status":"ok"|"error","stage":"dep|note|kb|folder|add","note_id":...,"media_id":...,
 *    "kb":...,"folder":...,"reused":true|false,"error":...}
 *   上游按退出码决定是否重试/报告，禁止忽略非 0 退出码继续宣布成功。
 */
const fs = require('fs');
const path = require('path');

// VPN 透明代理环境下 Node fetch 需要绕过 TLS 证书校验 + 更新检查文件重定向到可写目录
// 用户已设值时不覆盖，保留手动覆盖能力
if (!process.env.NODE_TLS_REJECT_UNAUTHORIZED) {
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
}
if (!process.env.IMA_LAST_CHECK_FILE) {
  process.env.IMA_LAST_CHECK_FILE = '/tmp/ima_last_check';
}

const IMA_API_PATH = process.env.IMA_API_PATH ||
  path.join(__dirname, '..', '..', 'ima-skill', 'ima_api.cjs');

const NOTE_FOLDER = '结构化答题技巧';
const KB_NAME = '总分总';
const KB_FOLDER = '00_结构化考官思维';

function report(obj) {
  console.log(JSON.stringify(obj));
}

function requireDependencies() {
  if (!fs.existsSync(IMA_API_PATH)) {
    report({ status: 'error', stage: 'dep', error: `ima_api.cjs 不存在: ${IMA_API_PATH}（可用 IMA_API_PATH 覆盖）` });
    process.exit(2);
  }
  const { imaApi } = require(IMA_API_PATH);
  return { imaApi };
}

// ── 幂等状态 ──
function stateFileOf(mdPath) {
  return path.join(path.dirname(path.resolve(mdPath)), '.ima_upload_state.json');
}
function stateKeyOf(mdPath, title) {
  return `${path.resolve(mdPath)}|${title}`;
}
function loadState(file) {
  try {
    const obj = JSON.parse(fs.readFileSync(file, 'utf-8'));
    return obj && typeof obj === 'object' ? obj : {};
  } catch {
    return {};
  }
}
function saveState(file, obj) {
  try {
    const tmp = `${file}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(obj, null, 2));
    fs.renameSync(tmp, file);
    return true;
  } catch {
    console.warn(`⚠️ 状态文件写入失败（幂等保护降级）: ${file}`);
    return false;
  }
}

async function main() {
  const argv = process.argv.slice(2);
  const fresh = argv.includes('--fresh');
  const positional = argv.filter((a) => a !== '--fresh');
  const mdPath = positional[0];
  const noteTitle = positional[1];
  if (!mdPath || !noteTitle) {
    report({ status: 'error', stage: 'usage', error: '用法: node upload_to_ima.js "<mdFilePath>" "<noteTitle>" [--fresh]' });
    process.exit(1);
  }

  let markdownContent;
  try {
    markdownContent = fs.readFileSync(mdPath, 'utf-8');
  } catch (err) {
    report({ status: 'error', stage: 'file', error: `md 文件读取失败: ${mdPath} (${err.code || err.message})` });
    process.exit(1);
  }

  const { imaApi } = requireDependencies();

  const stateFile = stateFileOf(mdPath);
  const stateKey = stateKeyOf(mdPath, noteTitle);
  const state = loadState(stateFile);
  const prev = !fresh && state[stateKey];

  // ── 1. 创建 IMA 笔记（幂等: 已有 note_id 则复用，绝不重复创建） ──
  let noteId;
  let reused = false;
  if (prev && prev.note_id) {
    noteId = prev.note_id;
    reused = true;
    if (prev.kb_done) {
      console.log(`✅ 历史上传已完成，幂等跳过全部 API 调用: note_id ${noteId}`);
      report({ status: 'ok', stage: 'add', note_id: noteId, kb: KB_NAME, reused: true });
      process.exit(0);
    }
    console.log(`♻️ 复用已创建笔记（上次知识库同步未完成）: note_id ${noteId}`);
  } else {
    const noteData = JSON.parse(await imaApi('openapi/note/v1/import_doc', {
      content_format: 1,
      content: markdownContent,
      folder_name: NOTE_FOLDER,
    }));
    if (noteData.code !== 0) {
      report({ status: 'error', stage: 'note', error: `IMA 笔记创建失败: ${noteData.msg}` });
      process.exit(2);
    }
    noteId = noteData.data.note_id;
    // 创建成功立即落盘: 此后任何失败，重试都复用该 note_id，不再重复建笔记
    state[stateKey] = { note_id: noteId, kb_done: false, updated_at: new Date().toISOString() };
    saveState(stateFile, state);
    console.log(`✅ IMA 笔记 note_id: ${noteId}`);
  }

  // ── 2. 搜索知识库 ──
  const kbData = JSON.parse(await imaApi('openapi/wiki/v1/search_knowledge_base', {
    query: KB_NAME, cursor: '', limit: 20,
  }));
  const targetKB = ((kbData.data && kbData.data.info_list) || [])
    .find((k) => k.kb_name && k.kb_name.includes(KB_NAME));
  if (!targetKB) {
    report({ status: 'error', stage: 'kb', note_id: noteId, reused, error: `未找到「${KB_NAME}」知识库，笔记已创建（重试将复用 note_id，不会重复建笔记）` });
    process.exit(3);
  }
  console.log(`✅ 知识库: ${targetKB.kb_name} ${targetKB.kb_id}`);

  // ── 3. 搜索目标文件夹（缺失则加到库根目录，仍是成功） ──
  const folderData = JSON.parse(await imaApi('openapi/wiki/v1/search_knowledge', {
    query: KB_FOLDER, knowledge_base_id: targetKB.kb_id, cursor: '',
  }));
  const targetFolder = ((folderData.data && folderData.data.info_list) || [])
    .find((f) => f.title && f.title.includes(KB_FOLDER));
  const folderId = targetFolder ? targetFolder.media_id : null;
  if (!folderId) console.warn(`⚠️ 未找到「${KB_FOLDER}」文件夹，将添加到知识库根目录`);

  // ── 4. 添加到知识库 ──
  const addBody = {
    media_type: 11,
    note_info: { content_id: noteId },
    title: noteTitle,
    knowledge_base_id: targetKB.kb_id,
  };
  if (folderId) addBody.folder_id = folderId;
  const addData = JSON.parse(await imaApi('openapi/wiki/v1/add_knowledge', addBody));
  if (addData.code !== 0) {
    report({ status: 'error', stage: 'add', note_id: noteId, reused, error: `知识库同步失败: ${addData.msg}（重试将复用 note_id，不会重复建笔记）` });
    process.exit(3);
  }

  // ── 5. 全部成功，落盘完成状态（此后重试零 API 调用直接成功） ──
  state[stateKey] = { note_id: noteId, kb_done: true, updated_at: new Date().toISOString() };
  saveState(stateFile, state);
  report({ status: 'ok', stage: 'add', note_id: noteId, media_id: addData.data.media_id, kb: targetKB.kb_name, folder: folderId ? KB_FOLDER : '根目录', reused });
  process.exit(0);
}

main().catch((err) => {
  report({ status: 'error', stage: 'unexpected', error: `${err.code || ''} ${err.message}`.trim() });
  process.exit(2);
});
