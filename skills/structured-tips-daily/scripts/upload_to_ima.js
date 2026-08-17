#!/usr/bin/env node
/**
 * upload_to_ima.js v2 -- 将「结构化答题技巧·每日一练」内容上传到 IMA 笔记并同步知识库
 *
 * 用法:
 *   node upload_to_ima.js "<md文件路径>" "<笔记标题>"
 *
 * 依赖:
 *   ima_api.cjs（默认 <skill>/../ima-skill/ima_api.cjs，可用环境变量 IMA_API_PATH 覆盖）
 *   依赖检查先于任何网络调用。
 *
 * 退出码:
 *   0  笔记创建 + 知识库同步均成功（文件夹缺失时降级到库根目录仍算 0）
 *   1  用法错误 / md 文件不存在或不可读
 *   2  依赖缺失 / IMA 笔记创建失败
 *   3  笔记已创建，但知识库同步失败（部分成功，note_id 已给出）
 *
 * 输出契约:
 *   stdout 最后一行是结构化 JSON:
 *   {"status":"ok"|"error","stage":"dep|note|kb|folder|add","note_id":...,"media_id":...,"kb":...,"folder":...,"error":...}
 *   上游按退出码决定是否重试/报告，禁止忽略非 0 退出码继续宣布成功。
 */
const fs = require('fs');
const path = require('path');

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

async function main() {
  const mdPath = process.argv[2];
  const noteTitle = process.argv[3];
  if (!mdPath || !noteTitle) {
    report({ status: 'error', stage: 'usage', error: '用法: node upload_to_ima.js "<mdFilePath>" "<noteTitle>"' });
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

  // ── 1. 创建 IMA 笔记 ──
  const noteData = JSON.parse(await imaApi('openapi/note/v1/import_doc', {
    content_format: 1,
    content: markdownContent,
    folder_name: NOTE_FOLDER,
  }));
  if (noteData.code !== 0) {
    report({ status: 'error', stage: 'note', error: `IMA 笔记创建失败: ${noteData.msg}` });
    process.exit(2);
  }
  const noteId = noteData.data.note_id;
  console.log(`✅ IMA 笔记 note_id: ${noteId}`);

  // ── 2. 搜索知识库 ──
  const kbData = JSON.parse(await imaApi('openapi/wiki/v1/search_knowledge_base', {
    query: KB_NAME, cursor: '', limit: 20,
  }));
  const targetKB = ((kbData.data && kbData.data.info_list) || [])
    .find((k) => k.kb_name && k.kb_name.includes(KB_NAME));
  if (!targetKB) {
    report({ status: 'error', stage: 'kb', note_id: noteId, error: `未找到「${KB_NAME}」知识库，笔记未同步` });
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
    report({ status: 'error', stage: 'add', note_id: noteId, error: `知识库同步失败: ${addData.msg}` });
    process.exit(3);
  }
  report({ status: 'ok', stage: 'add', note_id: noteId, media_id: addData.data.media_id, kb: targetKB.kb_name, folder: folderId ? KB_FOLDER : '根目录' });
  process.exit(0);
}

main().catch((err) => {
  report({ status: 'error', stage: 'unexpected', error: `${err.code || ''} ${err.message}`.trim() });
  process.exit(2);
});
