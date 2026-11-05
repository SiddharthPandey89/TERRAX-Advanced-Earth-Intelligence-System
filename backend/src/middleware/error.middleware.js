const errorMiddleware = (err, req, res, next) => {
if (res.headersSent) {
next(err);
return;
}
console.error(err);
const statusCode = Number(err?.statusCode ?? err?.status);
const status = Number.isInteger(statusCode) && statusCode >= 400 && statusCode <= 599
? statusCode
: 500;
const isDevelopment = process.env.NODE_ENV !== 'production';
const hasSafeMessage = err?.message && (isDevelopment || status < 500);
const response = {
success: false,
message: hasSafeMessage ? err.message : 'Internal Server Error',
};
if (isDevelopment && err?.stack) {
response.stack = err.stack;
}
res.status(status).json(response);
};
export default errorMiddleware;
