#!/usr/bin/env node
// MathJax runs in a separate process. No shell interpolation or network assets.
import { createRequire } from 'node:module';
import { realpathSync } from 'node:fs';
import { mkdir, rename, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';

export async function render(request) {
    let { expression, output, fontSize = 16, foreground = '#ffffff', padding = 4 } = request;
    if (typeof expression !== 'string' || !expression.trim() || expression.length > 65536)
        throw new Error('Expected a nonempty mathematical expression under 64 KiB.');
    if (typeof output !== 'string' || !output.endsWith('.svg'))
        throw new Error('Expected an SVG output path.');
    if (!Number.isFinite(fontSize) || fontSize < 1 || fontSize > 512
        || !Number.isFinite(padding) || padding < 0 || padding > 100
        || !/^#[0-9a-f]{6}$/i.test(foreground))
        throw new Error('Invalid formula size, padding or foreground color.');

    const data = process.env.XDG_DATA_HOME || join(homedir(), '.local/share');
    const runtime = process.env.DOTS_MATH_RUNTIME || join(data, 'dots-hyperland/math');
    const require = createRequire(join(runtime, 'package.json'));
    const MathJax = require('mathjax');
    for (const [start, end] of [['$$', '$$'], ['$', '$'], ['\\[', '\\]'], ['\\(', '\\)']]) {
        if (expression.startsWith(start) && expression.endsWith(end)) {
            expression = expression.slice(start.length, -end.length);
            break;
        }
    }
    await MathJax.init({
        loader: { load: ['input/tex', 'output/svg', 'ui/safe'] },
        tex: { packages: { '[-]': ['autoload', 'require'] } },
        svg: { fontCache: 'none' }
    });
    const container = await MathJax.tex2svgPromise(expression, { display: true, em: fontSize, ex: fontSize / 2 });
    const adaptor = MathJax.startup.adaptor;
    const svg = adaptor.firstChild(container);
    if (adaptor.serializeXML(svg).includes('data-mjx-error='))
        throw new Error('MathJax could not render this expression.');
    const viewBox = adaptor.getAttribute(svg, 'viewBox').split(/\s+/).map(Number);
    const scale = fontSize / 1000;
    const border = padding / scale;
    adaptor.setAttribute(svg, 'viewBox', [viewBox[0] - border, viewBox[1] - border,
        viewBox[2] + 2 * border, viewBox[3] + 2 * border].join(' '));
    adaptor.setAttribute(svg, 'width', `${viewBox[2] * scale + 2 * padding}px`);
    adaptor.setAttribute(svg, 'height', `${viewBox[3] * scale + 2 * padding}px`);
    const result = adaptor.serializeXML(svg).replaceAll('currentColor', foreground);
    if (/<(?:script|foreignObject|a)\b/i.test(result) || /(?:href|src)="(?:https?:|file:|data:)/i.test(result))
        throw new Error('Unsupported external content in formula.');
    await mkdir(dirname(output), { recursive: true });
    const temporary = `${output}.${process.pid}.tmp`;
    await writeFile(temporary, result, { mode: 0o600 });
    await rename(temporary, output);
    return output;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === realpathSync(process.argv[1])) {
    try {
        let input = '';
        for await (const chunk of process.stdin) {
            input += chunk;
            if (input.length > 131072) throw new Error('Formula request is too large.');
        }
        console.log(await render(JSON.parse(input)));
    } catch (error) {
        console.error(`[Formula renderer] ${error.message}`);
        process.exitCode = 1;
    }
}
