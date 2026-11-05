import app from './src/app.js';
import config from './src/config/env.js';

const server = app.listen(config.PORT, () => {
  console.log(`Earth GeoIntelligence backend listening on port ${config.PORT}.`);
});

server.on('error', (error) => {
  console.error('Backend server failed to start:', error.message);
  process.exitCode = 1;
});
