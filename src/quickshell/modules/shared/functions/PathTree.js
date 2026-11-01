.pragma library

function count(nodes) {
    return nodes.reduce((total, node) => total + (node.path ? 1 : 0) + count(node.children || []), 0);
}

function flatten(groups, expanded, query) {
    const terms = query.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().split(/\s+/).filter(Boolean);
    function matches(node) {
        const haystack = [node.title, node.path, ...(node.uses || []), ...(node.tags || [])].join(" ").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        return terms.every(term => haystack.includes(term));
    }
    function prune(node, inherited) {
        const direct = inherited || !terms.length || matches(node);
        const children = (node.children || []).map(child => prune(child, direct)).filter(Boolean);
        return direct || children.length ? Object.assign({}, node, {children: children}) : null;
    }
    const output = [];
    function visit(node, depth, lines, last) {
        const open = !!terms.length || !!expanded[node.id];
        output.push({node: node, depth: depth, lines: lines, last: last, expanded: open});
        if (open) node.children.forEach((child, index) => visit(child, depth + 1, [...lines, !last], index === node.children.length - 1));
    }
    const filtered = groups.map(group => prune(group, false)).filter(Boolean);
    filtered.forEach((group, index) => visit(group, 0, [], index === filtered.length - 1));
    return output;
}
