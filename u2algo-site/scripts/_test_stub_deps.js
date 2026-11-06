'use strict';
// Test-only preload (node -r): stubs the three npm deps server.js requires at
// module load so the HTTP integration test runs without `npm ci`. The test
// starts the server with no SUPABASE_*/DATABASE_URL env, so none of these
// stubs is ever called — they only have to resolve.
const Module = require('module');

const STUBS = {
  '@supabase/supabase-js': { createClient: () => { throw new Error('supabase stub called'); } },
  ws: function WebSocketStub() { throw new Error('ws stub called'); },
  pg: { Pool: function PoolStub() { throw new Error('pg stub called'); } },
};

const originalLoad = Module._load;
Module._load = function load(request, parent, isMain) {
  if (Object.prototype.hasOwnProperty.call(STUBS, request)) return STUBS[request];
  return originalLoad.call(this, request, parent, isMain);
};
