pragma Singleton
pragma ComponentBehavior: Bound

import qs.modules.common
import QtQuick
import Quickshell
import Quickshell.Io

// Render formulas asynchronously with upstream MathJax, preserving the public API.
Singleton {
    id: root
    readonly property int renderPadding: 4
    property list<string> processedHashes: []
    property var processedExpressions: ({})
    property var renderedImagePaths: ({})
    property var pending: ({})
    property string latexOutputPath: Directories.latexOutput

    signal renderFinished(string hash, string imagePath)

    function requestRender(expression) {
        const foreground = "#" + Appearance.colors.colOnLayer1.toString().slice(-6);
        const hash = Qt.md5(JSON.stringify(["mathjax-4", expression, Appearance.font.pixelSize.normal, foreground]));
        if (renderedImagePaths[hash]) {
            renderFinished(hash, renderedImagePaths[hash]);
            return [hash, false];
        }
        if (pending[hash]) return [hash, false];
        pending[hash] = true;
        processedExpressions[hash] = expression;
        const worker = renderWorker.createObject(root, {
            hash: hash,
            request: JSON.stringify({ expression: expression,
                output: `${root.latexOutputPath}/${hash}.svg`,
                fontSize: Appearance.font.pixelSize.normal,
                foreground: foreground, padding: root.renderPadding })
        });
        worker.running = true;
        return [hash, true];
    }

    Component {
        id: renderWorker
        Process {
            id: worker
            required property string hash
            required property string request
            property string resultPath: ""
            command: ["node", Quickshell.shellPath("scripts/math/render-latex.mjs")]
            stdinEnabled: true
            onStarted: {
                write(request);
                stdinEnabled = false;
            }
            stdout: StdioCollector { onStreamFinished: worker.resultPath = text.trim() }
            stderr: StdioCollector {
                onStreamFinished: { if (text.trim()) console.error("[LatexRenderer]", text); }
            }
            onExited: (exitCode, exitStatus) => {
                delete root.pending[hash];
                if (exitCode === 0 && resultPath) {
                    root.processedHashes.push(hash);
                    root.renderedImagePaths[hash] = resultPath;
                    root.renderFinished(hash, resultPath);
                } else {
                    delete root.processedExpressions[hash];
                    root.renderFinished(hash, "");
                }
                destroy();
            }
        }
    }
}
