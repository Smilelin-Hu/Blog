import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';

// 博客正文：沿用 docs/source 目录（保留 git 历史与规范路径），无 frontmatter，
// 标题取正文首个 H1，排序按文件名数字前缀。
const notes = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './docs/source' }),
});

export const collections = { notes };