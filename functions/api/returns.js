// 退貨原因登記 API — Cloudflare Pages Function + D1
// 一次性設定（Cloudflare dashboard）：
//   1. Workers & Pages → D1 → Create database「baojieh-returns」
//   2. Pages 專案 → Settings → Functions → D1 bindings → 變數名 DB → 選該資料庫
//   3. Pages 專案 → Settings → Environment variables → PIN = 自訂通行碼
const SCHEMA = `CREATE TABLE IF NOT EXISTS returns_cls (
  voucher_no TEXT PRIMARY KEY,
  cls TEXT NOT NULL,
  note TEXT DEFAULT '',
  filled_by TEXT DEFAULT '',
  ts TEXT DEFAULT ''
)`;

async function ensureTable(db) { await db.prepare(SCHEMA).run(); }

export async function onRequestGet({ env }) {
  if (!env.DB) return json({ error: 'D1 未綁定' }, 503);
  await ensureTable(env.DB);
  const { results } = await env.DB.prepare('SELECT * FROM returns_cls').all();
  return json({ rows: results });
}

export async function onRequestPost({ request, env }) {
  if (!env.DB) return json({ error: 'D1 未綁定' }, 503);
  if (env.PIN && request.headers.get('x-pin') !== env.PIN) return json({ error: 'PIN 錯誤' }, 401);
  const b = await request.json();
  if (!b.voucher_no || !['店家退貨', '拒收&劃單', '其他'].includes(b.cls)) return json({ error: '參數錯誤' }, 400);
  await ensureTable(env.DB);
  await env.DB.prepare(
    'INSERT INTO returns_cls (voucher_no, cls, note, filled_by, ts) VALUES (?1,?2,?3,?4,?5) ' +
    'ON CONFLICT(voucher_no) DO UPDATE SET cls=?2, note=?3, filled_by=?4, ts=?5'
  ).bind(b.voucher_no, b.cls, (b.note || '').slice(0, 100), (b.filled_by || '').slice(0, 20),
         new Date().toISOString()).run();
  return json({ ok: true });
}

const json = (o, status = 200) => new Response(JSON.stringify(o), {
  status, headers: { 'content-type': 'application/json;charset=utf-8' }
});
