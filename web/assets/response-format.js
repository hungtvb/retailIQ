/* Safe rich answers for the Week 1 chat: no raw HTML, no invented analytics. */
'use strict';
(function () {
  const EL = (tag, cls = '', value) => {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (value !== undefined) el.textContent = String(value);
    return el;
  };
  const safeLink = url => {
    try {
      if (typeof url !== 'string' || url.length > 2048 || url.trim() !== url) return null;
      const parsed = new URL(url);
      if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname ||
          parsed.username || parsed.password) return null;
      return parsed.href;
    } catch (_) { return null; }
  };
  function inline(target, input) {
    const text = String(input || '');
    const pattern = /\[([^\]]{1,200})\]\(([^\s)]+)\)|`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*/g;
    let previous = 0, m;
    while ((m = pattern.exec(text))) {
      if (m.index > previous) target.append(document.createTextNode(text.slice(previous, m.index)));
      let node;
      if (m[1] !== undefined) {
        const href = safeLink(m[2]);
        node = href ? EL('a', 'rich-link', m[1]) : document.createTextNode(m[0]);
        if (href) { node.href = href; node.rel = 'noopener noreferrer nofollow'; node.target = '_blank'; }
      } else if (m[3] !== undefined) node = EL('code', 'rich-inline-code', m[3]);
      else if (m[4] !== undefined) node = EL('strong', '', m[4]);
      else node = EL('em', '', m[5]);
      target.append(node);
      previous = pattern.lastIndex;
    }
    if (previous < text.length) target.append(document.createTextNode(text.slice(previous)));
  }
  function tableCells(line) {
    return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(v => v.trim());
  }
  function delimiter(line) {
    const cells = tableCells(line);
    return cells.length > 1 && cells.every(c => /^:?-{3,}:?$/.test(c));
  }
  function renderMarkdown(target, source) {
    target.replaceChildren();
    const lines = String(source || '').slice(0, 30000).replace(/\r\n?/g, '\n').split('\n');
    let index = 0;
    while (index < lines.length) {
      const line = lines[index], trimmed = line.trim();
      if (!trimmed) { index++; continue; }
      const fence = trimmed.match(/^```([\w#+-]*)/);
      if (fence) {
        index++;
        const code = [];
        while (index < lines.length && !/^\s*```/.test(lines[index])) code.push(lines[index++]);
        if (index < lines.length) index++;
        const block = EL('div', 'rich-code-block');
        const head = EL('div', 'rich-code-head');
        head.append(EL('span', '', fence[1] || 'Code'));
        const copy = EL('button', 'rich-copy', 'Copy');
        copy.type = 'button';
        copy.addEventListener('click', () => {
          if (navigator.clipboard?.writeText) navigator.clipboard.writeText(code.join('\n'))
            .then(() => { copy.textContent = 'Copied'; }).catch(() => { copy.textContent = 'Unavailable'; });
        });
        head.append(copy);
        const pre = EL('pre'), content = EL('code', '', code.join('\n'));
        pre.append(content); block.append(head, pre); target.append(block);
        continue;
      }
      if (index + 1 < lines.length && trimmed.includes('|') && delimiter(lines[index + 1])) {
        const headings = tableCells(trimmed);
        const table = EL('table', 'rich-md-table'), thead = EL('thead'), row = EL('tr');
        for (const h of headings.slice(0, 12)) { const th = EL('th'); inline(th,h); row.append(th); }
        thead.append(row); table.append(thead);
        const body = EL('tbody'); index += 2; let count = 0;
        while (index < lines.length && lines[index].includes('|') && lines[index].trim() && count < 80) {
          const tr = EL('tr');
          const cells = tableCells(lines[index]);
          for (let i=0;i<Math.min(headings.length,12);i++){const td=EL('td');inline(td,cells[i] || '');tr.append(td);}
          body.append(tr); index++;count++;
        }
        table.append(body); const scroll = EL('div','rich-table-scroll'); scroll.append(table); target.append(scroll);
        continue;
      }
      const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
      if (heading) { const el=EL('h' + Math.min(heading[1].length+2,5));inline(el,heading[2]);target.append(el);index++;continue; }
      if (/^[-*]\s+/.test(trimmed) || /^\d+[.)]\s+/.test(trimmed)) {
        const ordered=/^\d+[.)]\s+/.test(trimmed);
        const list=EL(ordered?'ol':'ul','rich-list');
        while(index < lines.length){
          const value=lines[index].trim();
          const m=value.match(ordered?/^\d+[.)]\s+(.+)$/:/^[-*]\s+(.+)$/);
          if(!m)break;
          const item=EL('li');inline(item,m[1]);list.append(item);index++;
        }
        target.append(list);continue;
      }
      if(/^>\s*/.test(trimmed)){const el=EL('blockquote');inline(el,trimmed.replace(/^>\s*/,''));target.append(el);index++;continue;}
      if(/^(-{3,}|\*{3,})$/.test(trimmed)){target.append(EL('hr'));index++;continue;}
      const parts=[trimmed];index++;
      while(index<lines.length && lines[index].trim() && !/^(#{1,3}\s|[-*]\s|\d+[.)]\s|>|\s*```)/.test(lines[index]) && !(index+1<lines.length && lines[index].includes('|') && delimiter(lines[index+1]))){
        parts.push(lines[index++].trim());
      }
      const p=EL('p');inline(p,parts.join(' '));target.append(p);
    }
    return target;
  }
  const number = n => Number(n).toLocaleString('en-US', {maximumFractionDigits:2});
  const validRow = (row, field, nonnegative = false) =>
    row !== null && typeof row === 'object' && !Array.isArray(row) &&
    Number.isSafeInteger(row[field]) && (!nonnegative || row[field] >= 0);
  function renderEvidence(target, result) {
    target.replaceChildren();
    // Render bounded, SQL-backed evidence only. Never coerce strings into KPIs.
    const records = Array.isArray(result?.records) && result.records.length <= 200 ? result.records : [];
    const intent = String(result?.intent || '');
    let metric = null, caption = '', labels = '';
    if (intent === 'stock' && records.length && records.every(r => validRow(r, 'available', true))) {
      metric = 'available';caption = 'Available stock'; labels = 'location';
    } else if (intent === 'revenue' && records.length && records.every(r => validRow(r, 'net_revenue_vnd'))) {
      metric = 'net_revenue_vnd';caption = 'Revenue by channel'; labels = 'channel';
    } else if (intent === 'top' && records.length && records.every(r => validRow(r, 'units_sold', true))) {
      metric = 'units_sold';caption = 'Top sellers · units'; labels = 'name';
    }
    const total = metric && records.reduce((sum, row) => sum + row[metric], 0);
    if (metric && records.length && Number.isSafeInteger(total)) {
      const section=EL('section','rich-evidence');
      const cards=EL('div','rich-metrics');
      const first = intent === 'top';
      const primary = first ? records[0][metric] : total;
      const primaryLabel = intent === 'top' ? 'Top product units sold' : intent === 'stock' ? 'Total available units' : 'Net revenue · VND';
      const values = [[primaryLabel,number(primary)],['Records',String(records.length)]];
      if(intent==='top' && records[0].name) values.push(['Top product',String(records[0].name)]);
      for(const [label,value] of values) {
        const card=EL('div','rich-metric');
        card.append(EL('span','rich-metric-label',label),EL('strong','rich-metric-value',value));
        cards.append(card);
      }
      section.append(cards);
      // Negative revenue is valid but a zero-based positive bar would mislead.
      if(records.length>1 && records.length<=12 &&
         records.every(row => row[metric] >= 0)) {
        const max=Math.max(0,...records.map(r => Number(r[metric])));
        if(max>0) {
          const chart=EL('div','rich-bars');
          chart.append(EL('h4','',caption));
          for(const row of records){
            const val=Math.max(0,Number(row[metric]));
            const item=EL('div','rich-bar-row');
            const name=EL('span','rich-bar-label',String(row[labels] || row.sku || '—'));
            const track=EL('div','rich-bar-track');
            const bar=EL('span','rich-bar-fill');bar.style.width=(100*val/max).toFixed(2)+'%';track.append(bar);
            item.append(name,track,EL('span','rich-bar-value',number(val)));chart.append(item);
          }
          section.append(chart);
        }
      }
      section.append(EL('p','rich-evidence-note','Calculated from returned SQL records · synthetic demo data'));
      target.append(section);
    }
    const contexts = Array.isArray(result?.contexts) ? result.contexts.slice(0, 100) : [];
    const sources = [...new Set(contexts
      .map(v => v && v.source)
      .filter(v => typeof v === 'string' && v.trim())
      .map(v => v.slice(0, 300)))];
    if (sources.length) {
      const group=EL('div','rich-citations');
      group.append(EL('span','','Sources'));
      for (const source of sources.slice(0,8)) group.append(EL('span','rich-citation',source));
      target.append(group);
    }
  }
  window.RetailIQFormat = Object.freeze({renderMarkdown,renderEvidence,safeLink});
})();
