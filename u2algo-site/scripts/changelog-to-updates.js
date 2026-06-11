#!/usr/bin/env node
// T-014: repo kökündeki CHANGELOG.md -> u2algo-site/updates.json
// Sıfır bağımlılık. Çalıştır: node u2algo-site/scripts/changelog-to-updates.js
// Çıktı commit'lenir (site statik kalır; runtime'da CHANGELOG parse edilmez).

const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');
const changelogPath = path.join(repoRoot, 'CHANGELOG.md');
const outPath = path.resolve(__dirname, '..', 'updates.json');

const text = fs.readFileSync(changelogPath, 'utf-8');

const entries = [];
let current = null;
let currentType = null;

for (const rawLine of text.split(/\r?\n/)) {
  const line = rawLine.trimEnd();

  const release = line.match(/^## \[([^\]]+)\]/);
  if (release) {
    const label = release[1];
    current = {
      date: /^\d{4}-\d{2}-\d{2}$/.test(label) ? label : null,
      label: label === 'Unreleased' ? 'Yakında' : label,
      items: []
    };
    entries.push(current);
    currentType = null;
    continue;
  }

  const section = line.match(/^### (.+)$/);
  if (section && current) {
    currentType = section[1].trim();
    continue;
  }

  const bullet = line.match(/^- (.+)$/);
  if (bullet && current) {
    current.items.push({ type: currentType || 'Değişiklik', text: bullet[1].trim() });
    continue;
  }

  // Girintili devam satırlarını önceki maddeye ekle
  if (current && current.items.length && /^\s{2,}\S/.test(rawLine)) {
    current.items[current.items.length - 1].text += ' ' + line.trim();
  }
}

const output = {
  generated_from: 'CHANGELOG.md',
  generated_at: new Date().toISOString().slice(0, 10),
  entries: entries.filter(e => e.items.length > 0)
};

fs.writeFileSync(outPath, JSON.stringify(output, null, 2) + '\n', 'utf-8');
console.log(`updates.json yazıldı: ${output.entries.length} grup, ` +
  `${output.entries.reduce((n, e) => n + e.items.length, 0)} madde`);
