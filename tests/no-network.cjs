// Formula rendering tests must work with only locally installed assets.
const deny = () => { throw new Error('Network access is disabled in this test'); };
for (const name of ['http', 'https']) {
    const transport = require(name);
    transport.request = transport.get = deny;
}
require('net').Socket.prototype.connect = deny;
global.fetch = deny;
