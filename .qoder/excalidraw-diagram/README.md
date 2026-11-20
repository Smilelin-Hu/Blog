# Excalidraw 绘图插件

用自然语言生成「有视觉论点」的 Excalidraw 图表（`.excalidraw` JSON），并可通过配套渲染脚本导出 PNG/SVG。适用于工作流、架构、概念总结类配图。

## 来源

- 源仓库：https://github.com/coleam00/excalidraw-diagram-skill （commit `8646fcc`，经 api.github.com / raw.githubusercontent.com 代理下载）
- Logo：本插件自绘 `assets/avatar.svg`（源仓库无 logo 文件）。

## 包含内容

- `skills/excalidraw-diagram/SKILL.md`：绘图方法论与 Excalidraw JSON 生成规范（原文保留）。
- `skills/excalidraw-diagram/references/color-palette.md`：配色单一事实来源。
- `skills/excalidraw-diagram/references/element-templates.md`：元素 JSON 模板。
- `skills/excalidraw-diagram/references/json-schema.md`：文件结构说明。
- `skills/excalidraw-diagram/references/render_excalidraw.py` + `render_template.html` + `pyproject.toml`：本地渲染脚本（依赖 playwright，需另行安装）。
- `skills/excalidraw-diagram/README.md`：源仓库 README（渲染器安装说明）。

## 省略说明

- 源仓库 `.gitignore` 未拷贝（与 skill 运行无关）。

## 使用提示

- 生成 `.excalidraw` 文件后可在 https://excalidraw.com 打开编辑。
- 渲染 PNG 需先按 skill 内 README 安装 playwright 依赖；未安装时仅产出 JSON 亦可用。

## 本机离线渲染适配（已验证）

- esm.sh 上 0.18.1 的 bundle 存在 404 子模块，改用固定版本 `@excalidraw/excalidraw@0.17.6` 的 `excalidraw.bundle.mjs`。
- `references/vendor_deps.py --proxy http://127.0.0.1:<port>` 一次性递归下载 bundle 及 react/node polyfill 依赖到 `references/vendor/`，并重写为相对导入；字体（Virgil/Cascadia/Assistant）存于 `vendor/excalidraw-assets/`。
- bundle 仅导出 default 对象，模板用 `import Lib from ...; const { exportToSvg } = Lib` 取 API。
- `render_excalidraw.py` 已适配：内置本地 HTTP 服务加载模板（规避 file:// CORS）、`domcontentloaded` 等待、`HTTPS_PROXY` 环境变量透传给 chromium。
- 渲染命令：`python3 render_excalidraw.py <file.excalidraw> --scale 1|2`。