const http = require('http');
const fs = require('fs');
const path = require('path');
const { createClient } = require('@supabase/supabase-js');
const WebSocket = require('ws');
const { Pool } = require('pg');

const root = __dirname;
const port = Number(process.env.PORT || 3000);
const supabaseUrl = process.env.SUPABASE_URL || '';
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY || '';
const databaseUrl = process.env.SUPABASE_DATABASE_URL || process.env.DATABASE_URL || '';
const localWaitlistPath = process.env.LOCAL_WAITLIST_PATH || path.join(root, 'data', 'waitlist_leads.jsonl');
const supabase = supabaseUrl && supabaseServiceRoleKey
  ? createClient(supabaseUrl, supabaseServiceRoleKey, {
      auth: { persistSession: false },
      realtime: { transport: WebSocket }
    })
  : null;
const pgPool = databaseUrl
  ? new Pool({
      connectionString: databaseUrl,
      max: 3,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 12000,
      ssl: databaseUrl.includes('sslmode=disable') ? false : { rejectUnauthorized: false }
    })
  : null;

function sendJson(res, status, payload) {
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff',
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
    'access-control-allow-headers': 'content-type'
  });
  res.end(JSON.stringify(payload));
}

function readJson(req, maxBytes = 4096) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => {
      body += chunk;
      if (Buffer.byteLength(body) > maxBytes) {
        reject(new Error('payload_too_large'));
        req.destroy();
      }
    });
    req.on('end', () => {
      try { resolve(body ? JSON.parse(body) : {}); }
      catch { reject(new Error('invalid_json')); }
    });
    req.on('error', reject);
  });
}

function normalizeEmail(value) {
  return String(value || '').trim().toLowerCase();
}

function validEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) && email.length <= 254;
}

async function appendLocalWaitlistLead(lead) {
  await fs.promises.mkdir(path.dirname(localWaitlistPath), { recursive: true });
  await fs.promises.appendFile(localWaitlistPath, `${JSON.stringify(lead)}\n`, 'utf8');
}

async function saveWaitlistLead(lead) {
  if (supabase) {
    try {
      const { error } = await supabase
        .from('waitlist_leads')
        .upsert(lead, { onConflict: 'email' });
      if (!error) return { ok: true, backend: 'supabase' };
      console.error('waitlist_insert_failed', error.message);
    } catch (err) {
      console.error('waitlist_insert_failed', err && err.message ? err.message : err);
    }
  }

  if (pgPool) {
    try {
      await pgPool.query(
        `insert into public.waitlist_leads (email, source, user_agent, consent, consent_at, created_at)
         values ($1, $2, $3, $4::boolean, $5::timestamptz, coalesce($6::timestamptz, now()))
         on conflict (email) do update set
           source = excluded.source,
           user_agent = excluded.user_agent,
           consent = excluded.consent,
           consent_at = excluded.consent_at,
           updated_at = now()`,
        [
          lead.email,
          lead.source || 'u2algo-site',
          lead.user_agent || null,
          lead.consent === true,
          lead.consent === true ? new Date().toISOString() : null,
          lead.created_at || null
        ]
      );
      return { ok: true, backend: 'postgres' };
    } catch (err) {
      console.error('waitlist_pg_insert_failed', err && err.message ? err.message : err);
    }
  }

  await appendLocalWaitlistLead({ ...lead, backend: supabase || pgPool ? 'local-jsonl-fallback' : 'local-jsonl' });
  return { ok: true, backend: supabase || pgPool ? 'local-jsonl-fallback' : 'local-jsonl' };
}

async function ensureWaitlistTable() {
  if (!pgPool) return;
  await pgPool.query('create extension if not exists pgcrypto');
  await pgPool.query(`
    create table if not exists public.waitlist_leads (
      id uuid primary key default gen_random_uuid(),
      email text unique not null,
      source text not null default 'u2algo-site',
      user_agent text,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now()
    )
  `);
  await pgPool.query(`
    create or replace function public.set_updated_at()
    returns trigger
    language plpgsql
    as $$
    begin
      new.updated_at = now();
      return new;
    end;
    $$
  `);
  await pgPool.query('drop trigger if exists waitlist_leads_set_updated_at on public.waitlist_leads');
  await pgPool.query(`
    create trigger waitlist_leads_set_updated_at
    before update on public.waitlist_leads
    for each row execute function public.set_updated_at()
  `);
  await pgPool.query('alter table public.waitlist_leads enable row level security');
  await pgPool.query(`
    do $$
    begin
      if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'waitlist_leads'
          and policyname = 'Allow public insert'
      ) then
        create policy "Allow public insert" on public.waitlist_leads
          for insert with check (true);
      end if;
    end
    $$
  `);
}

const types = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.txt': 'text/plain; charset=utf-8'
};

function safePath(urlPath) {
  let decoded;
  try {
    decoded = decodeURIComponent(urlPath.split('?')[0]);
  } catch {
    decoded = '/';
  }
  if (decoded === '/') decoded = '/index.html';
  const normalized = path.normalize(decoded).replace(/^([/\\])+/, '');
  const filePath = path.join(root, normalized);
  if (!filePath.startsWith(root)) return path.join(root, 'index.html');
  return filePath;
}

const server = http.createServer(async (req, res) => {
  const pathname = (req.url || '/').split('?')[0];

  if (req.method === 'OPTIONS' && pathname.startsWith('/api/')) {
    sendJson(res, 204, {});
    return;
  }

  if (pathname === '/healthz') {
    sendJson(res, 200, { ok: true, service: 'u2algo-site' });
    return;
  }

  if (pathname === '/api/waitlist/health') {
    let supabaseError = null;
    if (supabase) {
      try {
        const { data, error } = await supabase.from('waitlist_leads').select('id').limit(1);
        if (!error && Array.isArray(data)) {
          sendJson(res, 200, { ok: true, service: 'u2algo-waitlist', database: 'ready', backend: 'supabase', fallback: 'local-jsonl' });
          return;
        }
        supabaseError = error || new Error('unexpected_supabase_response');
      } catch (err) {
        supabaseError = err;
      }
    }

    if (pgPool) {
      try {
        await pgPool.query('select 1 from public.waitlist_leads limit 1');
        sendJson(res, 200, { ok: true, service: 'u2algo-waitlist', database: 'ready', backend: 'postgres', fallback: 'local-jsonl' });
        return;
      } catch (err) {
        sendJson(res, 200, { ok: true, service: 'u2algo-waitlist', database: 'unhealthy', backend: 'postgres', fallback: 'local-jsonl', error: err && err.code ? err.code : 'query_failed' });
        return;
      }
    }

    if (supabaseError) {
      sendJson(res, 200, {
        ok: true,
        service: 'u2algo-waitlist',
        database: 'unhealthy',
        backend: 'supabase',
        fallback: 'local-jsonl',
        error: supabaseError.code || supabaseError.name || 'query_failed'
      });
      return;
    }

    sendJson(res, 200, { ok: true, service: 'u2algo-waitlist', database: 'not_configured', fallback: 'local-jsonl' });
    return;
  }

  if (pathname === '/api/purchase-webhook' && req.method === 'POST') {
    try {
      await handlePurchaseWebhook(req, res);
    } catch (err) {
      const message = err && err.message ? err.message : 'internal_error';
      console.error('purchase_webhook_handler_failed', message);
      sendJson(res, 500, { ok: false, error: 'internal_error', detail: message });
    }
    return;
  }

  if (pathname === '/api/waitlist' && req.method === 'POST') {
    try {
      const payload = await readJson(req);
      const email = normalizeEmail(payload.email);
      if (!validEmail(email)) {
        sendJson(res, 400, { ok: false, error: 'invalid_email' });
        return;
      }
      // T-011: KVKK/GDPR consent zorunlu (P-003 W0 / G-P3-1)
      // consent:true olmadan insert reddedilir. Mevcut kayıtlar (consent=null) etkilenmez
      // (geriye dönük varsayım yok — UR-003 niti). Sadece yeni insert'lerde zorunlu.
      if (payload.consent !== true) {
        sendJson(res, 400, { ok: false, error: 'consent_required', hint: 'explicit consent: true required (KVKK/GDPR)' });
        return;
      }
      try {
        await ensureWaitlistTable();
      } catch (err) {
        console.error('waitlist_table_ensure_failed', err && err.message ? err.message : err);
      }
      const result = await saveWaitlistLead({
        email,
        source: 'u2algo-site',
        user_agent: String(req.headers['user-agent'] || '').slice(0, 500),
        consent: true,
        consent_at: new Date().toISOString(),
        created_at: new Date().toISOString()
      });
      sendJson(res, 200, { ok: true, backend: result.backend });
    } catch (err) {
      const message = err && err.message ? err.message : 'bad_request';
      sendJson(res, message === 'payload_too_large' ? 413 : 400, { ok: false, error: message });
    }
    return;
  }

  let filePath = safePath(req.url || '/');
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    filePath = path.join(root, 'index.html');
  }

  const ext = path.extname(filePath).toLowerCase();
  const headers = {
    'content-type': types[ext] || 'application/octet-stream',
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'strict-origin-when-cross-origin',
    'x-frame-options': 'DENY'
  };

  if (['.svg', '.ico', '.png', '.jpg', '.jpeg', '.webp', '.css', '.js'].includes(ext)) {
    headers['cache-control'] = 'public, max-age=86400';
  } else {
    headers['cache-control'] = 'public, max-age=300';
  }

  fs.createReadStream(filePath)
    .on('error', () => {
      res.writeHead(500, { 'content-type': 'text/plain; charset=utf-8' });
      res.end('Internal Server Error');
    })
    .pipe(res.writeHead(200, headers));
});

// === T-016: Lemon Squeezy Purchase Webhook (INERT BY DEFAULT) ===
// G-P3-B1/B4/B5 operatör onayı olmadan ASLA aktifleştirilmez.
// INERT durumda: 503 disabled_by_config döner. Geçerli imza + aktif flag
// olmadan hiçbir entitlement yazılmaz. Operatör B.1-B.4 onayı +
// LS_WEBHOOK_ENABLED=true + LEMONSQUEEZY_WEBHOOK_SECRET set edilince aktive olur.
const LS_WEBHOOK_ENABLED = process.env.LS_WEBHOOK_ENABLED === 'true';
const LS_WEBHOOK_SECRET = process.env.LEMONSQUEEZY_WEBHOOK_SECRET || '';
// Product ID → internal product mapping (T-016 finalize edilecek)
const LS_PRODUCT_MAP = {
  // LS product_id (numeric string) → 'wave1-premium' | 'wave1-pro' | ...
  // Operatör LS panel'den product_id alıp buraya ekleyecek (B.1 sonrası)
};

function verifyLsSignature(rawBody, signatureHeader, secret) {
  if (!signatureHeader || !secret) return false;
  const crypto = require('crypto');
  const hmac = crypto.createHmac('sha256', secret).update(rawBody).digest('hex');
  // timing-safe karşılaştırma — signatureHeader eşit uzunlukta olmayabilir, kontrol et
  const a = Buffer.from(hmac, 'utf8');
  let b;
  try { b = Buffer.from(signatureHeader, 'utf8'); } catch { return false; }
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

async function lsUpsertEntitlement({ email, product, orderRef, status = 'pending' }) {
  if (!email || !orderRef) throw new Error('email_and_order_ref_required');
  const row = {
    email,
    product: product || 'wave1-unknown',
    status,
    source: 'lemonsqueezy',
    order_ref: orderRef,
    granted_at: status === 'granted' ? new Date().toISOString() : null
  };
  if (supabase) {
    const { error } = await supabase
      .from('entitlements')
      .upsert(row, { onConflict: 'order_ref' });
    if (!error) return 'supabase';
    console.error('ls_entitlement_supabase_failed', error.message);
  }
  if (pgPool) {
    await pgPool.query(
      `insert into public.entitlements (email, product, status, source, order_ref, granted_at)
       values ($1, $2, $3, 'lemonsqueezy', $4, $5::timestamptz)
       on conflict (order_ref) do update set
         email = excluded.email,
         product = excluded.product,
         status = excluded.entitlements.status,
         granted_at = excluded.entitlements.granted_at,
         updated_at = now()`,
      [row.email, row.product, row.status, row.order_ref, row.granted_at]
    );
    return 'postgres';
  }
  throw new Error('no_db_backend_configured');
}

async function handlePurchaseWebhook(req, res) {
  // INERT GUARD 1: Feature flag
  if (!LS_WEBHOOK_ENABLED) {
    return sendJson(res, 503, { ok: false, error: 'disabled_by_config', hint: 'set LS_WEBHOOK_ENABLED=true (T-016 B.1-B.4 onayı sonrası)' });
  }
  // INERT GUARD 2: Secret configured
  if (!LS_WEBHOOK_SECRET) {
    return sendJson(res, 503, { ok: false, error: 'webhook_secret_not_configured' });
  }

  // Raw body (HMAC için JSON parse ÖNCESİ)
  const chunks = [];
  req.on('data', c => chunks.push(c));
  await new Promise((resolve, reject) => {
    req.on('end', resolve);
    req.on('error', reject);
  });
  const raw = Buffer.concat(chunks);

  // HMAC doğrula (timing-safe)
  const sig = String(req.headers['x-signature'] || '');
  if (!verifyLsSignature(raw, sig, LS_WEBHOOK_SECRET)) {
    return sendJson(res, 401, { ok: false, error: 'invalid_signature' });
  }

  // Parse event
  let event;
  try { event = JSON.parse(raw.toString('utf8')); }
  catch { return sendJson(res, 400, { ok: false, error: 'invalid_json' }); }

  const eventName = event && event.meta && event.meta.event_name;
  const orderAttrs = event && event.data && event.data.attributes;

  switch (eventName) {
    case 'order_created': {
      if (!orderAttrs || !orderAttrs.user_email || !orderAttrs.id) {
        return sendJson(res, 400, { ok: false, error: 'missing_required_fields' });
      }
      const product = LS_PRODUCT_MAP[String(orderAttrs.product_id)] || 'wave1-unknown';
      try {
        await lsUpsertEntitlement({
          email: orderAttrs.user_email,
          product,
          orderRef: String(orderAttrs.id),
          status: 'pending'
        });
      } catch (err) {
        console.error('ls_order_created_failed', err && err.message ? err.message : err);
        return sendJson(res, 500, { ok: false, error: 'entitlement_write_failed' });
      }
      // T-017 kuyruğuna düşer (runbook'a göre manuel grant yapılacak)
      // Onay e-postası: Resend entegrasyonu (B.4 kararına göre) — şimdilik stub
      return sendJson(res, 200, { ok: true, action: 'entitlement_pending', order_ref: orderAttrs.id, email: orderAttrs.user_email });
    }
    case 'order_refunded': {
      if (!orderAttrs || !orderAttrs.id) {
        return sendJson(res, 400, { ok: false, error: 'missing_required_fields' });
      }
      try {
        await lsUpsertEntitlement({
          email: orderAttrs.user_email,
          product: 'wave1-unknown',
          orderRef: String(orderAttrs.id),
          status: 'revoked'
        });
      } catch (err) {
        console.error('ls_order_refunded_failed', err && err.message ? err.message : err);
        return sendJson(res, 500, { ok: false, error: 'entitlement_revoke_failed' });
      }
      // T-017 revoke kuyruğuna düşer
      return sendJson(res, 200, { ok: true, action: 'entitlement_revoked', order_ref: orderAttrs.id });
    }
    case 'subscription_cancelled':
    case 'subscription_expired':
    case 'subscription_payment_failed': {
      // G-P3-B5 kararına göre: abonelik seçilirse expires_at işleme
      // Şimdilik (G-P3-B5 ertelendi): event logla, entitlement status değiştirme
      if (!orderAttrs || !orderAttrs.id) {
        return sendJson(res, 200, { ok: true, action: 'logged_only', event: eventName });
      }
      try {
        if (supabase) {
          await supabase.from('entitlements')
            .update({ status: 'expired', updated_at: new Date().toISOString() })
            .eq('order_ref', String(orderAttrs.id));
        } else if (pgPool) {
          await pgPool.query(
            `update public.entitlements set status='expired', updated_at=now() where order_ref=$1`,
            [String(orderAttrs.id)]
          );
        }
      } catch (err) {
        console.error('ls_subscription_event_failed', err && err.message ? err.message : err);
      }
      return sendJson(res, 200, { ok: true, action: 'entitlement_expired', event: eventName, order_ref: orderAttrs.id });
    }
    default:
      // Bilinmeyen event — logla, 200 dön (LS retry storm önleme)
      return sendJson(res, 200, { ok: true, action: 'ignored', event: eventName || 'unknown' });
  }
}

server.listen(port, '0.0.0.0', () => {
  console.log(`u2algo-site listening on ${port}`);
});
