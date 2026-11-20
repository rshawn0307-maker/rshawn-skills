/**
 * upload_to_ima.js
 * ================
 * 将"结构化每日一练"答题内容上传到 IMA 笔记 + 同步到知识库。
 *
 * 用法：
 *   node <skill-path>/scripts/upload_to_ima.js "<md文件路径>" "<笔记标题>"
 *
 * 参数：
 *   argv[2] = Markdown 文件路径（临时生成的 md 文件）
 *   argv[3] = 笔记标题（含时间戳，如 "指尖形式主义_20260723_153000"）
 *
 * 流程：读取 md -> 创建 IMA 笔记 -> 搜索"总分总"知识库 -> 搜索"00_结构化每日一练"文件夹 -> 添加到知识库
 * 上传失败不阻断主流程，在 stderr 输出警告即可。
 *
 * TLS 证书自愈（2026-08-22 固化）：
 *   ima.qq.com 服务器证书链不完整（缺中间证书），且其根证书 DigiCert Global Root G2
 *   不在 node 内置 CA 库中，node fetch 直接报 unable to get local issuer certificate。
 *   修复：脚本同目录放 _ima_ca_bundle.pem（中间证书 + 根证书），启动时若检测到
 *   证书包且外部未设 NODE_EXTRA_CA_CERTS，则带该环境变量重启自身（env 必须在进程
 *   启动前设置，脚本内修改无效）。证书包缺失则按原行为运行并在 stderr 提示。
 */
const fs = require('fs');
const path = require('path');
const { imaApi } = require(path.join(__dirname, '..', '..', 'ima-skill', 'ima_api.cjs'));

// ── TLS 证书自愈：必要时带 NODE_EXTRA_CA_CERTS 重启自身 ──
(async function bootstrap() {
  if (!process.env.NODE_EXTRA_CA_CERTS) {
    const caBundle = path.join(__dirname, '_ima_ca_bundle.pem');
    if (fs.existsSync(caBundle)) {
      console.error('♻️ 启用 TLS 证书包:', caBundle);
      const { spawn } = require('child_process');
      const code = await new Promise((resolve) => {
        const rerun = spawn(process.execPath, [__filename, ...process.argv.slice(2)], {
          stdio: 'inherit',
          env: { ...process.env, NODE_EXTRA_CA_CERTS: caBundle }
        });
        rerun.on('close', resolve);
      });
      process.exit(code);
    } else {
      console.error('⚠️ 未找到 _ima_ca_bundle.pem，若 fetch failed 请检查证书包是否在 scripts 目录');
    }
  }
  await main();
})().catch(err => console.error('⚠️ upload_to_ima.js 异常:', err.message));

async function main() {
  const mdPath = process.argv[2];
  const noteTitle = process.argv[3];

  if (!mdPath || !noteTitle) {
    console.error('Usage: node upload_to_ima.js "<mdFilePath>" "<noteTitle>"');
    process.exit(1);
  }

  const markdownContent = fs.readFileSync(mdPath, 'utf-8');

  // ── 1. 创建 IMA 笔记 ──
  const noteResp = await imaApi('openapi/note/v1/import_doc', {
    content_format: 1,
    content: markdownContent,
    folder_name: '结构化每日一练'
  });
  const noteData = JSON.parse(noteResp);
  if (noteData.code !== 0) {
    console.error('⚠️ IMA笔记创建失败:', noteData.msg);
    return;
  }
  const noteId = noteData.data.note_id;
  console.log('✅ IMA笔记 note_id:', noteId);

  // ── 2. 搜索"总分总"知识库 ──
  const kbResp = await imaApi('openapi/wiki/v1/search_knowledge_base', {
    query: '总分总', cursor: '', limit: 20
  });
  const kbData = JSON.parse(kbResp);
  const kbList = (kbData.data && kbData.data.info_list) || [];
  const targetKB = kbList.find(k => k.kb_name && k.kb_name.includes('总分总'));
  if (!targetKB) {
    console.error('⚠️ 未找到"总分总"知识库，跳过知识库同步');
    return;
  }
  console.log('✅ 知识库:', targetKB.kb_name, targetKB.kb_id);

  // ── 3. 在知识库中搜索目标文件夹 ──
  const folderResp = await imaApi('openapi/wiki/v1/search_knowledge', {
    query: '00_结构化每日一练',
    knowledge_base_id: targetKB.kb_id,
    cursor: ''
  });
  const folderData = JSON.parse(folderResp);
  const folderList = (folderData.data && folderData.data.info_list) || [];
  const targetFolder = folderList.find(f => f.title && f.title.includes('00_结构化每日一练'));
  const folderId = targetFolder ? targetFolder.media_id : null;
  if (!folderId) {
    console.error('⚠️ 未找到"00_结构化每日一练"文件夹，将添加到知识库根目录');
  } else {
    console.log('✅ 文件夹 folder_id:', folderId);
  }

  // ── 4. 将笔记添加到知识库 ──
  const addBody = {
    media_type: 11,
    note_info: { content_id: noteId },
    title: noteTitle,
    knowledge_base_id: targetKB.kb_id
  };
  if (folderId) addBody.folder_id = folderId;
  const addResp = await imaApi('openapi/wiki/v1/add_knowledge', addBody);
  const addData = JSON.parse(addResp);
  if (addData.code === 0) console.log('✅ 知识库同步成功 media_id:', addData.data.media_id);
  else console.error('⚠️ 知识库同步失败:', addData.msg);
}
// 入口统一由顶部 bootstrap 负责（含 TLS 证书自愈 respawn）

