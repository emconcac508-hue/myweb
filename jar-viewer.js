/* jar-viewer.js - khung xem mã nguồn JAR cho SentinelJar (nhúng vào tab Mã nguồn).
   Dùng:  JarViewer.mount(element, { zip, name, size, weight(line), canDecompile }) */
(function () {
  const MIN_PLAN = 2; // PRO
  const JSZIP = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
  const svg = (d, w = 18, x = '') => `<svg viewBox="0 0 20 20" width="${w}" height="${w}" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" ${x}>${d}</svg>`;
  const IC = {
    chev: svg('<path d="M7 4l6 6-6 6"/>', 14),
    folder: svg('<path d="M2.5 5.5A1.5 1.5 0 014 4h3.2l1.6 1.8H16a1.5 1.5 0 011.5 1.5v7A1.5 1.5 0 0116 16H4a1.5 1.5 0 01-1.5-1.5z"/>'),
    file: svg('<path d="M5 2.5h6l4 4V17a.5.5 0 01-.5.5h-9A.5.5 0 015 17z"/><path d="M11 2.5v4h4"/>'),
    sliders: svg('<path d="M3 6h6M13 6h4M3 14h2M9 14h8"/><circle cx="11" cy="6" r="2"/><circle cx="7" cy="14" r="2"/>', 22),
    play: svg('<path d="M6 4.5l9 5.5-9 5.5z"/>', 22),
    lock: svg('<rect x="4.5" y="9" width="11" height="8" rx="1.5"/><path d="M7 9V6.5a3 3 0 016 0V9"/>', 16)
  };
  const CSS = `
.jv-box{--line:rgba(255,255,255,.1);--text:#e3e8f5;--mute:#8d97b5;--teal:#5ab4ff;--sel:rgba(255,157,60,.14);--selt:#ffb36b;--panel:rgba(255,255,255,.045);--card:#141a2e;
 width:100%;height:min(640px,calc(100vh - 290px));min-height:440px;background:rgba(12,17,32,.9);backdrop-filter:blur(14px);color:var(--text);border-radius:16px;display:flex;flex-direction:column;overflow:hidden;font:14px/1.5 Sora,Inter,system-ui,"Segoe UI",sans-serif;border:1px solid var(--line)}
.jv-box *{box-sizing:border-box;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.22) transparent}
.jv-h{display:flex;align-items:center;gap:14px;padding:12px 20px;border-bottom:1px solid var(--line)}
.jv-ic{width:40px;height:40px;border-radius:50%;background:rgba(255,157,60,.16);display:grid;place-items:center;font-size:20px}
.jv-h b{display:block;font-size:17px;line-height:1.2}.jv-h small{color:var(--mute)}.jv-sp{flex:1}
.jv-tabs{display:flex;gap:4px;margin-left:10px;padding-left:14px;border-left:1px solid var(--line)}
.jv-tab{border:0;background:none;color:var(--mute);padding:7px 12px;border-radius:9px;cursor:pointer;font:inherit}
.jv-tab.on{background:var(--panel);color:var(--text);font-weight:600;box-shadow:inset 0 0 0 1px var(--line)}
.jv-n{background:rgba(90,180,255,.18);color:#9fd0ff;border-radius:10px;padding:1px 8px;font-size:12px;margin-left:6px;font-weight:600}
.jv-m{flex:1;display:grid;grid-template-columns:320px 1fr;min-height:0}
.jv-a{border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0}
.jv-a input{margin:12px;padding:9px 12px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.05);color:var(--text);font:inherit;outline:0}
.jv-a input:focus{border-color:var(--teal);box-shadow:0 0 0 3px rgba(90,180,255,.18)}
.jv-t{overflow:auto;padding:0 6px 12px;flex:1}
.jv-r{display:flex;align-items:center;gap:6px;height:30px;padding-right:8px;border-radius:7px;cursor:pointer;white-space:nowrap}
.jv-r:hover{background:var(--panel)}.jv-r.sel{background:var(--sel)}
.jv-g{width:14px;flex:none;color:var(--mute);display:grid;place-items:center}.jv-g svg{transition:transform .12s}.jv-r.open .jv-g svg{transform:rotate(90deg)}
.jv-i{flex:none;display:grid;place-items:center;color:#7c86a3}.jv-i.d{color:var(--teal)}.jv-i.cls{color:#b79cff}
.jv-nm{overflow:hidden;text-overflow:ellipsis}.jv-r.sel .jv-nm{color:var(--selt);font-weight:600}
.jv-k.hide{display:none}
.jv-s{position:relative;display:flex;flex-direction:column;min-width:0;min-height:0}
.jv-bar{display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid var(--line);min-height:52px}
.jv-bar span{flex:1;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.jv-b{border:1px solid var(--line);background:var(--panel);border-radius:10px;padding:6px 12px;cursor:pointer;font:inherit;color:var(--text)}.jv-b:hover{background:rgba(255,255,255,.09)}
.jv-e{margin:auto;text-align:center;color:var(--mute)}.jv-e b{display:block;color:var(--text);font-size:18px;margin-bottom:2px}
.jv-c{flex:1;overflow:auto;margin:0;display:none;color:#d5dbee;font:13px/1.6 "JetBrains Mono",ui-monospace,Menlo,Consolas,monospace}
.jv-c.raw{white-space:pre-wrap;word-break:break-all;padding:16px 22px;color:#aab3cc}
.jv-l{display:flex}.jv-l i{flex:none;width:58px;padding-right:14px;text-align:right;color:#5d6784;user-select:none;font-style:normal;background:rgba(255,255,255,.03)}
.jv-l span{padding-left:14px;white-space:pre}
.jv-c em{font-style:normal}.jv-c .k{color:#c4a5ff;font-weight:600}.jv-c .s{color:#6ee7b7}.jv-c .c{color:#6b7694}.jv-c .n{color:#ffb36b}
.jv-pop{position:absolute;inset:0;display:none;align-items:center;justify-content:center;z-index:2;background:rgba(6,9,20,.35)}
.jv-card{width:min(430px,92%);background:var(--card);border-radius:18px;box-shadow:0 18px 50px rgba(0,0,0,.55),0 0 0 1px var(--line);padding:22px 22px 18px}
.jv-card h3{margin:0 0 16px;text-align:center;font-size:18px;font-weight:600}
.jv-o{display:flex;gap:14px;align-items:flex-start;width:100%;text-align:left;padding:14px 16px;margin-bottom:12px;border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.03);cursor:pointer;font:inherit;color:var(--text)}
.jv-o:hover{background:rgba(255,255,255,.07)}.jv-o.first{border-color:rgba(90,180,255,.5);background:rgba(90,180,255,.1)}
.jv-o .oi{color:var(--teal);margin-top:2px}.jv-o b{display:block;font-weight:600;color:#bfe0ff}.jv-o small{color:var(--mute);font-size:13px}
.jv-o.lock{opacity:.65}.jv-o.lock b{color:var(--text)}
.jv-tag{margin-left:8px;font:600 11px inherit;background:rgba(255,193,77,.18);color:#ffc14d;border-radius:6px;padding:1px 6px;vertical-align:1px}
.jv-pm{min-height:18px;text-align:center;color:#ffc14d;font-size:13px;margin:2px 0 0}
.jv-l.dg{background:rgba(255,93,108,.12)}.jv-l.dg span{color:#ff8f9a}.jv-l.wn{background:rgba(255,193,77,.09)}.jv-l.wn span{color:#ffc14d}
@media (max-width:760px){.jv-m{grid-template-columns:1fr}.jv-a{max-height:38%;border-right:0;border-bottom:1px solid var(--line)}.jv-tabs{display:none}}`;

  const esc = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const td = new TextDecoder();
  const KW = 'abstract|assert|boolean|break|byte|case|catch|char|class|continue|default|do|double|else|enum|extends|final|finally|float|for|if|implements|import|instanceof|int|interface|long|new|package|private|protected|public|return|short|static|super|switch|this|throw|throws|try|void|volatile|while|null|true|false';
  const HL = new RegExp('("(?:[^"\\\\]|\\\\.)*")|(//.*$)|\\b(\\d+[lLfFdD]?)\\b|\\b(' + KW + ')\\b', 'g');
  const hl = (l) => /^\s*(\/\*|\*|\/\/)/.test(l) ? '<em class="c">' + esc(l) + '</em>'
    : esc(l).replace(HL, (m, s, c, n) => '<em class="' + (s ? 's' : c ? 'c' : n ? 'n' : 'k') + '">' + m + '</em>');

  function loadZip() {
    if (window.JSZip) return Promise.resolve();
    return new Promise((ok, no) => {
      const s = document.createElement('script');
      s.src = JSZIP; s.onload = ok; s.onerror = () => no(new Error('Không tải được JSZip'));
      document.head.appendChild(s);
    });
  }

  // Đọc .class (chưa decompile): tên lớp, field, method, chuỗi hằng
  function parseClass(buf) {
    const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
    let o = 0;
    const u1 = () => dv.getUint8(o++);
    const u2 = () => { const v = dv.getUint16(o); o += 2; return v; };
    const u4 = () => { const v = dv.getUint32(o); o += 4; return v; };
    if (u4() !== 0xcafebabe) throw new Error('Không phải file .class');
    u2(); const major = u2(), n = u2(), cp = new Array(n);
    for (let i = 1; i < n; i++) {
      const t = u1();
      if (t === 1) { const l = u2(); cp[i] = { t, s: td.decode(buf.subarray(o, o + l)) }; o += l; }
      else if (t === 5 || t === 6) { o += 8; i++; }
      else if ([3, 4, 9, 10, 11, 12, 17, 18].includes(t)) { cp[i] = { t, a: dv.getUint16(o) }; o += 4; }
      else if ([7, 8, 16, 19, 20].includes(t)) cp[i] = { t, a: u2() };
      else if (t === 15) o += 3;
      else throw new Error('Constant pool lỗi');
    }
    const utf = (i) => (cp[i] && cp[i].s) || '?';
    const cls = (i) => (cp[i] ? utf(cp[i].a) : '?');
    u2(); const name = cls(u2()), sup = cls(u2()), ifs = [];
    for (let c = u2(); c > 0; c--) ifs.push(cls(u2()));
    const members = () => {
      const out = [];
      for (let c = u2(); c > 0; c--) {
        u2(); const nm = utf(u2()), ds = utf(u2());
        for (let a = u2(); a > 0; a--) { u2(); o += u4(); }
        out.push(nm + '  ' + ds);
      }
      return out;
    };
    const fields = members(), methods = members();
    return { major, name, sup, ifs, fields, methods, strings: cp.filter((x) => x && x.t === 1).map((x) => x.s) };
  }

  const valuesText = (c) => [
    '// class: ' + c.name + '   (Java major version ' + c.major + ')', '// extends: ' + c.sup,
    ...(c.ifs.length ? ['// implements: ' + c.ifs.join(', ')] : []),
    '', '// Fields (' + c.fields.length + ')', ...c.fields,
    '', '// Methods (' + c.methods.length + ')', ...c.methods,
    '', '// Giá trị / chuỗi (' + c.strings.length + ')', ...c.strings.slice(0, 3000)].join('\n');

  // Dạng thô như trong ảnh mẫu: ký tự in được giữ nguyên, còn lại thành dấu chấm
  const rawText = (b) => { let s = ''; const m = Math.min(b.length, 400000); for (let i = 0; i < m; i++) s += b[i] >= 32 && b[i] < 127 ? String.fromCharCode(b[i]) : '.'; return s; };
  const isText = (n) => /\.(txt|md|json|yml|yaml|xml|properties|mf|sf|cfg|toml|html|js|css|mcmeta|lang|java)$/i.test(n) || /MANIFEST\.MF$/i.test(n) || /LICENSE/i.test(n);

  async function mount(el, opts) {
    const file = { name: opts.name || 'file.jar', size: opts.size || 0 };
    const weight = opts.weight || (() => 0);
    if (!document.getElementById('jv-css')) {
      const st = document.createElement('style'); st.id = 'jv-css'; st.textContent = CSS; document.head.appendChild(st);
    }
    const root = el;
    root.innerHTML = `<div class="jv-box" role="dialog" aria-label="Xem mã nguồn JAR">
      <div class="jv-h"><div class="jv-ic">☕</div><div><b class="jv-title"></b><small class="jv-size"></small></div>
        <div class="jv-tabs"><button class="jv-tab on" data-t="files">Cây file</button>
        <button class="jv-tab" data-t="str">Chuỗi<span class="jv-n">…</span></button></div></div>
      <div class="jv-m"><div class="jv-a"><input placeholder="Tìm file…" aria-label="Tìm file"><div class="jv-t"></div></div>
        <div class="jv-s"><div class="jv-bar"><span>Chưa chọn file</span><button class="jv-b" hidden>Chọn thao tác</button></div>
          <div class="jv-e"><b>Chưa chọn file</b>Chọn một file ở cây bên trái để xem nội dung</div>
          <pre class="jv-c"></pre>
          <div class="jv-pop"><div class="jv-card"><h3>Bạn muốn làm gì?</h3>
            <button class="jv-o first" data-o="values"><span class="oi">${IC.sliders}</span><span><b class="jv-ov">Xem giá trị</b><small>Xem chuỗi, tên hàm và cờ trong class, không cần decompile.</small></span></button>
            <button class="jv-o" data-o="java"><span class="oi">${IC.play}</span><span><b>Đọc mã nguồn Java<span class="jv-tag" hidden>PRO</span></b><small>Decompile class này để xem nó làm gì.</small></span></button>
            <p class="jv-pm"></p></div></div></div></div></div>`;
    const $ = (s) => root.querySelector(s);
    const onKey = (e) => { if (e.key === 'Escape' && root.isConnected && $('.jv-pop').style.display === 'flex') hidePop(); };
    if (el._jvk) document.removeEventListener('keydown', el._jvk);
    el._jvk = onKey; document.addEventListener('keydown', onKey);
    $('.jv-title').textContent = file.name || 'file.jar';
    $('.jv-size').textContent = (file.size / 1024).toFixed(0) + ' KB';

    const wc = (l) => { const w = weight(l); return w >= 15 ? ' dg' : w >= 5 ? ' wn' : ''; };
    const show = (text, mode) => {
      $('.jv-e').style.display = 'none';
      const c = $('.jv-c'); c.style.display = 'block'; c.className = 'jv-c ' + (mode || 'lines');
      if (mode === 'raw') c.textContent = text;
      else c.innerHTML = text.split('\n').map((l, i) => '<div class="jv-l' + wc(l) + '"><i>' + (i + 1) + '</i><span>' + (mode === 'java' ? hl(l) : esc(l)) + '</span></div>').join('');
      c.scrollTop = 0;
    };

    let zip, files = [], cur = null, strs = new Set(), canDec = false, tab = 'files', info = null;
    zip = opts.zip;
    zip.forEach((p, e) => { if (!e.dir) files.push(p); });

    // Gói của user lấy từ server (server vẫn kiểm tra lại khi decompile)
    canDec = opts.canDecompile !== false;
    function lockUI() {
      const o = $('[data-o=java]'); o.classList.toggle('lock', !canDec); $('.jv-tag').hidden = canDec;
    }
    lockUI();

    const pm = (t) => { $('.jv-pm').textContent = t || ''; };
    const showPop = () => { pm(); $('.jv-pop').style.display = 'flex'; };
    function hidePop() { $('.jv-pop').style.display = 'none'; }
    $('.jv-pop').addEventListener('mousedown', (e) => e.target === $('.jv-pop') && hidePop());
    $('.jv-b').onclick = showPop;

    function build(list, all) {
      const tree = {};
      list.forEach((p) => { let n = tree; p.split('/').forEach((k, i, a) => { n = n[k] = n[k] || (i === a.length - 1 ? { __f: p } : {}); }); });
      const render = (node, depth) => {
        const box = document.createElement('div');
        Object.keys(node).sort((a, b) => (!!node[a].__f - !!node[b].__f) || a.localeCompare(b)).forEach((k) => {
          const v = node[k], row = document.createElement('div');
          row.className = 'jv-r'; row.style.paddingLeft = (6 + depth * 18) + 'px';
          if (v.__f) {
            row.innerHTML = '<span class="jv-g"></span><span class="jv-i' + (/\.class$/i.test(k) ? ' cls' : '') + '">' + IC.file + '</span><span class="jv-nm">' + esc(k) + '</span>';
            row.onclick = () => openFile(v.__f, row); box.append(row);
          } else {
            const open = all || depth < 2;
            row.innerHTML = '<span class="jv-g">' + IC.chev + '</span><span class="jv-i d">' + IC.folder + '</span><span class="jv-nm">' + esc(k) + '/</span>';
            const kids = render(v, depth + 1); kids.className = 'jv-k' + (open ? '' : ' hide'); row.classList.toggle('open', open);
            row.onclick = () => { kids.classList.toggle('hide'); row.classList.toggle('open'); }; box.append(row, kids);
          }
        });
        return box;
      };
      $('.jv-t').replaceChildren(render(tree, 0));
    }
    build(files, false);
    $('.jv-a input').oninput = (e) => {
      const v = e.target.value.trim().toLowerCase();
      build(v ? files.filter((p) => p.toLowerCase().includes(v)) : files, !!v);
    };

    async function openFile(p, row) {
      root.querySelectorAll('.jv-r.sel').forEach((r) => r.classList.remove('sel')); row && row.classList.add('sel');
      cur = p; tab = 'files'; setTabs(); hidePop(); info = null;
      $('.jv-bar span').textContent = p;
      const isClass = /\.class$/i.test(p);
      $('.jv-b').hidden = !isClass;
      try {
        const b = await zip.file(p).async('uint8array');
        if (isClass) {
          show(rawText(b), 'raw');
          try { info = parseClass(b); $('.jv-ov').textContent = 'Xem giá trị (' + info.strings.length + ')'; } catch (_) { $('.jv-ov').textContent = 'Xem giá trị'; }
          showPop();
        } else if (b.length > 2e6) show('// File quá lớn để xem (' + b.length + ' byte)', 'raw');
        else show(isText(p) ? td.decode(b) : rawText(b), isText(p) ? 'lines' : 'raw');
      } catch (e) { show('// Không đọc được file này: ' + e.message, 'raw'); }
    }

    $('[data-o=values]').onclick = () => {
      if (!info) return pm('Không đọc được cấu trúc class này.');
      hidePop(); show(valuesText(info), 'lines');
    };
    $('[data-o=java]').onclick = async () => {
      if (!canDec) return pm('Đọc mã Java cần gói PRO trở lên.');
      const p = cur; pm('Đang decompile…');
      try {
        // Class lồng nhau (Ten$Con.class) phải decompile cùng lớp ngoài và các lớp con
        const dir = p.includes('/') ? p.slice(0, p.lastIndexOf('/') + 1) : '';
        const outer = p.slice(dir.length).split('$')[0].replace(/\.class$/, '');
        let main = dir + outer + '.class'; if (!zip.file(main)) main = p;
        const rel = files.filter((f) => f !== main && f.startsWith(dir + outer + '$') && f.endsWith('.class') && !f.slice(dir.length).includes('/')).slice(0, 59);
        const fd = new FormData();
        for (const f of [main, ...rel]) fd.append('files', await zip.file(f).async('blob'), f.slice(dir.length));
        const r = await fetch('/api/decompile', { method: 'POST', body: fd, credentials: 'include' });
        const d = await r.json().catch(() => ({}));
        if (p !== cur) return;
        if (r.ok) { hidePop(); show((main !== p ? '// Đã decompile cả lớp ngoài ' + main.slice(dir.length) + ' (gồm các lớp con)\n' : '') + d.text, 'java'); }
        else pm(d.detail || 'Decompile thất bại.');
      } catch (e) { pm('Không kết nối được server.'); }
    };

    function setTabs() { root.querySelectorAll('.jv-tab').forEach((t) => t.classList.toggle('on', t.dataset.t === tab)); }
    root.querySelector('[data-t=files]').onclick = () => {
      tab = 'files'; setTabs();
      if (cur) openFile(cur); else { $('.jv-c').style.display = 'none'; $('.jv-e').style.display = ''; }
    };
    root.querySelector('[data-t=str]').onclick = () => {
      tab = 'str'; setTabs(); hidePop(); $('.jv-b').hidden = true; $('.jv-bar span').textContent = 'Chuỗi trong jar';
      show([...strs].slice(0, 5000).join('\n') || '// Đang quét chuỗi…', 'lines');
    };

    // Gom chuỗi từ mọi .class, chia nhỏ để không treo trang
    (async () => {
      let k = 0;
      for (const p of files) {
        if (!/\.class$/i.test(p)) continue;
        try { parseClass(await zip.file(p).async('uint8array')).strings.forEach((s) => s.length > 3 && strs.add(s)); } catch (_) {}
        if (++k % 40 === 0) { $('.jv-n').textContent = strs.size; await new Promise((r) => setTimeout(r)); if (!root.isConnected) return; }
      }
      $('.jv-n').textContent = strs.size;
    })();
  }

  window.JarViewer = { mount };
})();
