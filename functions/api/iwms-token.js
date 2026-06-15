// Cloudflare Pages Function — iWMS Token 存取
// KV binding: IWMS_KV
// Secret:     IWMS_SECRET

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'content-type',
};

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS });
}

export async function onRequestPost({ request, env }) {
  const kv = env.IWMS_KV;
  const secret = env.IWMS_SECRET;
  if (!kv) return json({ ok: false, error: 'KV 未綁定' }, 503);

  const body = await request.json().catch(() => ({}));
  if (secret && body.secret !== secret)
    return json({ ok: false, error: '認證失敗' }, 401);

  const token = body.token || '';
  if (!token) return json({ ok: false, error: '無 token' }, 400);

  await kv.put('iwms_token', token, { expirationTtl: 86400 });
  return json({ ok: true });
}

export async function onRequestGet({ request, env }) {
  const kv = env.IWMS_KV;
  const secret = env.IWMS_SECRET;
  if (!kv) return json({ ok: false, error: 'KV 未綁定' }, 503);

  const url = new URL(request.url);
  if (secret && url.searchParams.get('secret') !== secret)
    return json({ ok: false, error: '認證失敗' }, 401);

  const token = await kv.get('iwms_token');
  if (!token) return json({ ok: false, error: 'Token 不存在或已過期' }, 404);
  return json({ ok: true, token });
}

const json = (o, s = 200) => new Response(JSON.stringify(o), {
  status: s, headers: { 'content-type': 'application/json;charset=utf-8', ...CORS }
});
