/* Scoped visual identities. Never use model output as a CSS class directly. */
'use strict';
(function () {
  const TYPES = Object.freeze({
    supervisor: { name: 'Retail Supervisor', short: 'Supervisor', icon: 'compass', color: '#1c3656' },
    sales: { name: 'Sales Agent', short: 'Sales', icon: 'trending-up', color: '#16845c' },
    inventory: { name: 'Inventory Agent', short: 'Inventory', icon: 'package', color: '#2866c7' },
    product: { name: 'Product Agent', short: 'Product', icon: 'tag', color: '#7953bd' },
    iq: { name: 'IQ · RetailIQ', short: 'IQ', icon: 'sparkles', color: '#26415e' },
    user: { name: 'You', short: 'You', icon: 'user', color: '#667085' }
  });
  const PATHS = {
    compass: '<circle cx="12" cy="12" r="9"/><path d="m15.4 8.6-2.4 4.4-4.4 2.4 2.4-4.4z"/>',
    'trending-up': '<path d="m3 17 6-6 4 4 7-8"/><path d="M15 7h5v5"/>',
    package: '<path d="m12 2 9 5v10l-9 5-9-5V7z"/><path d="M3 7l9 5 9-5M12 12v10"/>',
    tag: '<path d="M3 4h9l9 9-8 8-10-10z"/><circle cx="8" cy="8" r="1.4"/>',
    sparkles: '<path d="m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5z"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>'
  };
  function type(value, intent) {
    const s = String(value || '').toLowerCase();
    const i = String(intent || '').toLowerCase();
    if (/supervisor|decision|replenish/.test(s) || i === 'decision') return 'supervisor';
    if (/sales|revenue|top/.test(s) || i === 'top' || i === 'revenue') return 'sales';
    if (/inventory|stock/.test(s) || i === 'stock') return 'inventory';
    if (/product|rag/.test(s) || i === 'product') return 'product';
    return 'iq';
  }
  function icon(id) {
    const shape = PATHS[TYPES[id]?.icon] || PATHS.sparkles;
    const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.8');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    // The icon markup is a constant, never model- or user-supplied.
    svg.innerHTML = shape;
    return svg;
  }
  function avatar(id) {
    const safe = TYPES[id] ? id : 'iq';
    const node = document.createElement('span');
    node.className = 'agent-avatar agent-avatar-' + safe;
    node.setAttribute('aria-hidden', 'true');
    node.append(icon(safe));
    return node;
  }
  function apply(node,id) {
    const safe = TYPES[id] ? id : 'iq';
    node.dataset.agent = safe;
    return safe;
  }
  window.RetailIQIdentity = Object.freeze({ TYPES, type, icon, avatar, apply });
})();
