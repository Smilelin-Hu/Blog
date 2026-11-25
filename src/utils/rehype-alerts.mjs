// 提示框：把 `> [!NOTE] / [!TIP] / [!WARNING] / [!IMPORTANT] / [!CAUTION]`
// 引用块渲染为彩色 alert（沿用 docsify flexible-alerts 的中文标签）。
const LABELS = {
  NOTE: '说明',
  TIP: '技巧',
  WARNING: '注意',
  IMPORTANT: '重要',
  CAUTION: '警告',
};

const textOf = (node) =>
  node.type === 'text' ? node.value : (node.children ?? []).map(textOf).join('');

export default function rehypeAlerts() {
  return (tree) => {
    const out = [];
    for (const child of tree.children ?? []) {
      if (child.type === 'element' && child.tagName === 'blockquote') {
        const first = child.children?.find((c) => c.type === 'element');
        const m = first && textOf(first).match(/^\s*\[!(\w+)\]\s*/);
        if (m && LABELS[m[1].toUpperCase()]) {
          const kind = m[1].toUpperCase();
          // 去掉首段中的 [!TYPE] 标记
          const strip = (n) => {
            if (n.type === 'text') {
              n.value = n.value.replace(/^\s*\[!\w+\]\s*/, '');
              return;
            }
            for (const c of n.children ?? []) strip(c);
          };
          strip(first);
          const label = {
            type: 'element',
            tagName: 'p',
            properties: { className: ['alert-label'] },
            children: [{ type: 'text', value: LABELS[kind] }],
          };
          out.push({
            type: 'element',
            tagName: 'div',
            properties: { className: ['alert', `alert-${kind.toLowerCase()}`] },
            children: [label, ...child.children],
          });
          continue;
        }
      }
      out.push(child);
    }
    tree.children = out;
  };
}