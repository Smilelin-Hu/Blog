import type { CollectionEntry } from 'astro:content';

export type Note = CollectionEntry<'notes'>;

/** 规范路径：glob loader 的 id 会被 slugify 小写化，路由/内链须用原始 filePath。 */
export function pathOf(entry: Note): string {
  const fp = entry.filePath ?? entry.id;
  return fp.replace(/^docs\/source\//, '').replace(/\.md$/, '');
}

/** 文件名/目录名数字前缀感知的排序（01- xxx 排在 2- xxx 前，中文按拼音序兜底）。 */
export function cmpName(a: string, b: string): number {
  const na = parseInt(a, 10);
  const nb = parseInt(b, 10);
  if (!Number.isNaN(na) && !Number.isNaN(nb) && na !== nb) return na - nb;
  if (!Number.isNaN(na) && Number.isNaN(nb)) return -1;
  if (Number.isNaN(na) && !Number.isNaN(nb)) return 1;
  return a.localeCompare(b, 'zh-CN');
}

export function sortNotes(entries: Note[]): Note[] {
  return [...entries].sort((a, b) => {
    const pa = pathOf(a).split('/');
    const pb = pathOf(b).split('/');
    for (let i = 0; i < Math.min(pa.length, pb.length); i++) {
      if (pa[i] !== pb[i]) return cmpName(pa[i], pb[i]);
    }
    return pa.length - pb.length;
  });
}

/** 正文首个 H1 作为标题；缺失时退回文件名。 */
export function titleOf(entry: Note): string {
  const m = (entry.body ?? '').match(/^#\s+(.+)$/m);
  if (m) return m[1].trim();
  const name = pathOf(entry).split('/').pop() ?? pathOf(entry);
  return name.replace(/^\d+-/, '');
}

export function dirOf(entry: Note): string {
  const p = pathOf(entry);
  const i = p.lastIndexOf('/');
  return i <= 0 ? '' : p.slice(0, i);
}

/** 文件名主干（保留序号前缀），侧边栏与 README 目录链接文本保持一致。 */
export function stemOf(entry: Note): string {
  return pathOf(entry).split('/').pop() ?? pathOf(entry);
}

export interface SeriesMeta {
  slug: string;
  label: string;
  icon: string;
  blurb: string;
  /** wip = 系列尚未完成，目录处备注「待完成」 */
  status?: 'wip';
}

/** 顶层系列目录的展示元信息（图标与一句话简介）。 */
export const SERIES: SeriesMeta[] = [
  { slug: 'AI-Infra', label: 'AI Infra', icon: '🏗️', blurb: '训练 / 性能 / 推理 / 平台 / 数据与后训练五大主题的系统笔记' },
  { slug: 'GPU算子优化', label: 'GPU 算子优化', icon: '⚡', blurb: '从硬件到算子的优化主线：HIP / Profiling / GEMM / Attention' },
  { slug: '国产GPGPU推理优化', label: '国产 GPGPU 推理优化', icon: '🧮', blurb: '国产算力适配方法论与推理引擎横向评测', status: 'wip' },
  { slug: '大模型', label: '大模型', icon: '🧠', blurb: '理论 / 微调量化 / 多模态 / 部署工程与开源模型实战' },
  { slug: 'agent', label: 'Agent', icon: '🤖', blurb: 'RAG 全栈、智能体构建与企业级 Agent 手册' },
  { slug: 'vibecoding', label: 'Vibe Coding', icon: '💻', blurb: 'AI 编程入门到规范驱动开发的实践路径' },
  { slug: 'AI工具全景', label: 'AI 工具全景', icon: '🧰', blurb: '模型 API / CLI / MCP / Skills / RAG 框架选型盘点' },
  { slug: '推荐系统', label: '推荐系统', icon: '📊', blurb: '协同过滤到生成式推荐的演进笔记' },
  { slug: '传统CV算法', label: '传统 CV 算法', icon: '👁️', blurb: '边缘检测与机器学习基础' },
  { slug: '视频结构化', label: '视频结构化', icon: '🎬', blurb: '视频理解与结构化 pipeline' },
  { slug: '产品经理', label: '产品经理', icon: '📐', blurb: 'JTBD / Mom Test / 双钻模型与 AI 产品实战' },
  { slug: '论文阅读', label: '论文阅读', icon: '📄', blurb: '论文精读笔记' },
  { slug: '推理优化课程册', label: '推理优化课程册', icon: '📚', blurb: 'llm-inference-opt 课程按课次整理的实验笔记：机制、实验闭环与判读纪律' },
  { slug: '训练系统课程册', label: '训练系统课程册', icon: '🏋️', blurb: 'ai-infra-p5 数据与后训练课程按课次整理的实验笔记' },
  { slug: '系统性能课程册', label: '系统性能课程册', icon: '⏱️', blurb: 'ai-systems-perf-v2 性能工程课程按课次整理的实验笔记' },
  { slug: '平台工程课程册', label: '平台工程课程册', icon: '🛰️', blurb: 'ai-platform-eng 平台工程课程按课次整理的实验笔记' },
];

/** 系列序号：按 SERIES 策展顺序 1..N，目录展示统一带序号。 */
export function seriesNum(slug: string): number {
  const i = SERIES.findIndex((s) => s.slug === slug);
  return i >= 0 ? i + 1 : SERIES.length + 1;
}

export function metaOf(slug: string): SeriesMeta | undefined {
  return SERIES.find((s) => s.slug === slug);
}

export function seriesOf(entry: Note): SeriesMeta {
  const top = pathOf(entry).split('/')[0];
  return SERIES.find((s) => s.slug === top) ?? { slug: top, label: top, icon: '📁', blurb: '' };
}

export interface TreeNode {
  name: string;
  path: string;
  dirs: TreeNode[];
  files: Note[];
}

/** 由笔记集合构建目录树（侧边栏用），README 作为目录索引文件置顶。 */
export function buildTree(entries: Note[]): TreeNode[] {
  const root: TreeNode = { name: '', path: '', dirs: [], files: [] };
  for (const e of sortNotes(entries)) {
    const parts = pathOf(e).split('/');
    let node = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const path = parts.slice(0, i + 1).join('/');
      let child = node.dirs.find((d) => d.path === path);
      if (!child) {
        child = { name: parts[i], path, dirs: [], files: [] };
        node.dirs.push(child);
      }
      node = child;
    }
    node.files.push(e);
  }
  const sortNode = (n: TreeNode) => {
    n.dirs.sort((a, b) => cmpName(a.name, b.name));
    // 子系列顺序跟随本目录 README 的出场顺序（学习路径），未提及的排最后
    const readme = n.files.find((f) => pathOf(f) === `${n.path}/README`);
    if (readme?.body) {
      const body = readme.body;
      const pos = (name: string) => {
        const cands = [`](${name}/`, `](${name})`, `](./${name}/`, `](./${name})`, `/${name}/`, `/${name})`];
        const hits = cands.map((c) => body.indexOf(c)).filter((i) => i >= 0);
        return hits.length ? Math.min(...hits) : Number.MAX_SAFE_INTEGER;
      };
      n.dirs.sort((a, b) => pos(a.name) - pos(b.name) || cmpName(a.name, b.name));
    }
    n.files.sort((a, b) => {
      const ra = pathOf(a).endsWith('/README');
      const rb = pathOf(b).endsWith('/README');
      if (ra !== rb) return ra ? -1 : 1;
      return cmpName(pathOf(a).split('/').pop() ?? '', pathOf(b).split('/').pop() ?? '');
    });
    n.dirs.forEach(sortNode);
  };
  sortNode(root);
  // 顶层系列按策展顺序排列，保证序号递增；未收录目录排最后
  root.dirs.sort((a, b) => seriesNum(a.name) - seriesNum(b.name) || cmpName(a.name, b.name));
  return root.dirs;
}

/** 同目录上下篇（README 不参与上下篇，仅作返回目录）。 */
export function pagerOf(entry: Note, all: Note[]) {
  const dir = dirOf(entry);
  const siblings = sortNotes(all.filter((e) => dirOf(e) === dir && !pathOf(e).endsWith('/README')));
  const i = siblings.findIndex((e) => pathOf(e) === pathOf(entry));
  const readme = all.find((e) => pathOf(e) === (dir ? `${dir}/README` : 'README'));
  return {
    prev: i > 0 ? siblings[i - 1] : null,
    next: i >= 0 && i < siblings.length - 1 ? siblings[i + 1] : null,
    index: readme ?? null,
  };
}