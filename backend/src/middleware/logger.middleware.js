
const loggerMiddleware = (req, res, next) => {
  const startTime = process.hrtime.bigint();

  res.once('finish', () => {
    try {
      const timestamp = new Date().toISOString();
      const method = req.method || 'UNKNOWN';
      const url = req.originalUrl || req.url || '-';
      const statusCode = Number.isInteger(res.statusCode) ? res.statusCode : 500;
      const responseTime = Number(process.hrtime.bigint() - startTime) / 1e6;
      const contentLength = res.getHeader('content-length');
      const length = contentLength !== undefined && contentLength !== null
        ? `${contentLength}B`
        : '-';
      const message = `[${timestamp}] ${method} ${url} ${statusCode} - ${responseTime.toFixed(2)}ms - ${length}`;

      if (statusCode >= 500) {
        console.error(message);
      } else if (statusCode >= 400) {
        console.warn(message);
      } else {
        console.log(message);
      }
    } catch (loggingError) {
      console.error('Request logging failed:', loggingError.message);
    }
  });

  next();
};

export default loggerMiddleware;
