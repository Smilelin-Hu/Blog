// 内链重写：docsify 时代的站内链接迁移到 Astro 路由。
// 1) 绝对 /source/... 链接加 base 前缀（GH Pages 子路径部署）；
// 2) 相对 *.md 链接去掉扩展名（路由与目录结构同构）；
// 3) 其余站内绝对路径（如 /resume）加 base 前缀。
const walk = (node, fn) => {
  fn(node);
  for (const child of node.children ?? []) walk(child, fn);
};

export default function rehypeBlogLinks(base) {
  const prefix = base === '/' ? '' : base.replace(/\/$/, '');
  return (tree) => {
    walk(tree, (node) => {
      if (node.type !== 'element' || node.tagName !== 'a') return;
      const href = node.properties?.href;
      if (typeof href !== 'string' || !href) return;
      if (/^(https?:)?\/\//.test(href) || href.startsWith('#') || href.startsWith('mailto:')) return;
      let next = href;
      if (next.startsWith('/source/')) {
        next = prefix + next.replace(/\.md$/, '');
      } else if (next.startsWith('/')) {
        next = prefix + next.replace(/\.md$/, '');
      } else if (next.endsWith('.md')) {
        next = next.slice(0, -3);
      }
      node.properties.href = next;
    });
  };
}