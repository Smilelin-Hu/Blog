import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import rehypeSlug from 'rehype-slug';
import rehypeAutolinkHeadings from 'rehype-autolink-headings';
import rehypeExternalLinks from 'rehype-external-links';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeTableWrap from './src/utils/rehype-table-wrap.mjs';
import rehypeReferences from './src/utils/rehype-references.mjs';
import rehypeBlogLinks from './src/utils/rehype-blog-links.mjs';
import rehypeAlerts from './src/utils/rehype-alerts.mjs';

const BASE = '/Blog';

export default defineConfig({
  site: 'https://swpucwf.github.io',
  base: BASE,
  integrations: [tailwind()],
  experimental: {
    contentLayer: true,
  },
  markdown: {
    shikiConfig: {
      langAlias: { cuda: 'cpp', text: 'plaintext' },
      themes: {
        light: 'github-light',
        dark: 'github-dark',
      },
      defaultColor: 'light',
      wrap: false,
    },
    remarkPlugins: [remarkMath],
    rehypePlugins: [
      rehypeSlug,
      [rehypeAutolinkHeadings, { behavior: 'wrap' }],
      [rehypeExternalLinks, { target: '_blank', rel: ['nofollow', 'noopener'] }],
      rehypeKatex,
      rehypeTableWrap,
      rehypeReferences,
      rehypeAlerts,
      [rehypeBlogLinks, BASE],
    ],
  },
});