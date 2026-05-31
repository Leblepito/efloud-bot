const http = require('http');
const fs = require('fs');
const path = require('path');
const { createClient } = require('@supabase/supabase-js');
const WebSocket = require('ws');

const root = __dirname;
const port = Number(process.env.PORT || 3000);
const supabaseUrl = process.env.SUPABASE_URL || '';
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY || '';
const supabase = supabaseUrl && supabaseServiceRoleKey
  ? createClient(supabaseUrl, supabaseServiceRoleKey, {
      auth: { persistSession: false },
      realtime: { transport: WebSocket }
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

async function ensureWaitlistTable() {
  // Supabase REST cannot create tables; table is expected to exist.
  // SQL for dashboard:
  // create table if not exists public.waitlist_leads (
  //   id uuid primary key default gen_random_uuid(),
  //   email text unique not null,
  //   source text not null default 'u2algo-site',
  //   user_agent text,
  //   created_at timestamptz not null default now()
  // );
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
    if (!supabase) {
      sendJson(res, 503, { ok: false, service: 'u2algo-waitlist', database: 'missing_supabase_env' });
      return;
    }
    try {
      const { error } = await supabase.from('waitlist_leads').select('id', { count: 'exact', head: true }).limit(1);
      if (error) {
        sendJson(res, 503, { ok: false, service: 'u2algo-waitlist', database: 'unhealthy', error: error.code || 'query_failed' });
        return;
      }
      sendJson(res, 200, { ok: true, service: 'u2algo-waitlist', database: 'ready' });
    } catch (err) {
      sendJson(res, 503, { ok: false, service: 'u2algo-waitlist', database: 'unreachable' });
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
      if (!supabase) {
        sendJson(res, 503, { ok: false, error: 'waitlist_not_configured' });
        return;
      }
      await ensureWaitlistTable();
      const { error } = await supabase
        .from('waitlist_leads')
        .upsert({
          email,
          source: 'u2algo-site',
          user_agent: String(req.headers['user-agent'] || '').slice(0, 500)
        }, { onConflict: 'email' });
      if (error) {
        console.error('waitlist_insert_failed', error.message);
        sendJson(res, 500, { ok: false, error: 'waitlist_insert_failed' });
        return;
      }
      sendJson(res, 200, { ok: true });
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

server.listen(port, '0.0.0.0', () => {
  console.log(`u2algo-site listening on ${port}`);
});
