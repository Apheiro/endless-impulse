.pragma library

function overlaps(a, b) {
    return a.x < b.x + b.width && a.x + a.width > b.x
        && a.y < b.y + b.height && a.y + a.height > b.y;
}

// Sweep the whole motion, rather than just checking its destination: even a
// fast pointer jump must not tunnel through another monitor. At a collision,
// keep the tangential movement so the tile can slide along the neighbour.
function move(rect, target, obstacles) {
    let x = rect.x, y = rect.y;
    let dx = target.x - x, dy = target.y - y;
    const epsilon = 1e-9;
    for (let step = 0; step < obstacles.length * 2 + 2; step++) {
        if (Math.abs(dx) + Math.abs(dy) < epsilon) break;
        let time = 1, blockX = false, blockY = false, found = false;
        for (const other of obstacles) {
            let enterX = -Infinity, exitX = Infinity;
            let enterY = -Infinity, exitY = Infinity;
            if (dx > 0) {
                enterX = (other.x - x - rect.width) / dx;
                exitX = (other.x + other.width - x) / dx;
            } else if (dx < 0) {
                enterX = (other.x + other.width - x) / dx;
                exitX = (other.x - x - rect.width) / dx;
            } else if (x + rect.width <= other.x || x >= other.x + other.width) continue;
            if (dy > 0) {
                enterY = (other.y - y - rect.height) / dy;
                exitY = (other.y + other.height - y) / dy;
            } else if (dy < 0) {
                enterY = (other.y + other.height - y) / dy;
                exitY = (other.y - y - rect.height) / dy;
            } else if (y + rect.height <= other.y || y >= other.y + other.height) continue;
            const entry = Math.max(enterX, enterY);
            const exit = Math.min(exitX, exitY);
            if (entry < -epsilon || entry > 1 || entry >= exit - epsilon) continue;
            if (entry < time - epsilon || !found && entry <= time) {
                time = Math.max(0, entry);
                blockX = enterX >= enterY - epsilon;
                blockY = enterY >= enterX - epsilon;
                found = true;
            } else if (Math.abs(entry - time) < epsilon) {
                blockX = blockX || enterX >= enterY - epsilon;
                blockY = blockY || enterY >= enterX - epsilon;
            }
        }
        x += dx * time;
        y += dy * time;
        if (!found) break;
        dx = blockX ? 0 : dx * (1 - time);
        dy = blockY ? 0 : dy * (1 - time);
    }
    return {x: x, y: y};
}
