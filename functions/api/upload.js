export async function onRequestPost({ request, env }) {
  const token = env.GITHUB_TOKEN;
  if (!token) return Response.json({ ok: false, error: 'GITHUB_TOKEN 未設定' }, { status: 500 });

  const REPO = 'waynechiang0101/baojieh-dashboard';

  let formData;
  try { formData = await request.formData(); }
  catch (e) { return Response.json({ ok: false, error: '解析表單失敗' }, { status: 400 }); }

  const file = formData.get('file');
  const label = (formData.get('label') || '').slice(0, 60);
  if (!file) return Response.json({ ok: false, error: '無檔案' }, { status: 400 });

  const MAX = 20 * 1024 * 1024; // 20MB
  const bytes = await file.arrayBuffer();
  if (bytes.byteLength > MAX)
    return Response.json({ ok: false, error: '檔案超過 20MB 限制' }, { status: 413 });

  // base64 encode
  const u8 = new Uint8Array(bytes);
  let b64 = '';
  const chunk = 8192;
  for (let i = 0; i < u8.length; i += chunk)
    b64 += String.fromCharCode(...u8.slice(i, i + chunk));
  const content = btoa(b64);

  // 檔名加時間戳避免衝突
  const ts = new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-');
  const safeName = file.name.replace(/[^a-zA-Z0-9.一-鿿_-]/g, '_');
  const path = `data/uploads/${ts}_${safeName}`;

  // 檢查是否已存在（取得 sha）
  const headers = {
    Authorization: `token ${token}`,
    'Content-Type': 'application/json',
    'User-Agent': 'baojieh-dashboard'
  };
  let sha;
  const check = await fetch(`https://api.github.com/repos/${REPO}/contents/${path}`, { headers });
  if (check.ok) sha = (await check.json()).sha;

  const msg = label ? `上傳: ${safeName} (${label})` : `上傳: ${safeName}`;
  const body = JSON.stringify({ message: msg, content, ...(sha ? { sha } : {}) });

  const res = await fetch(`https://api.github.com/repos/${REPO}/contents/${path}`, {
    method: 'PUT', headers, body
  });

  if (res.ok) {
    return Response.json({
      ok: true, path,
      url: `https://github.com/${REPO}/blob/main/${path}`
    });
  }
  const err = await res.text();
  return Response.json({ ok: false, error: err }, { status: 500 });
}
