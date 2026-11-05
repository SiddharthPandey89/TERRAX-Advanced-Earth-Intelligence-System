
const SENSITIVE_KEY_PATTERN =
  /(password|passwd|secret|token|api[_-]?key|authorization|cookie|credential|database[_-]?url)/i;

const SENSITIVE_VALUE_PATTERNS = [
  /\bBearer\s+[A-Za-z0-9._~+/=-]+/gi,
  /\b(password|passwd|secret|token|api[_-]?key|authorization|cookie|credential|database[_-]?url)\s*[:=]\s*(['"]?)[^\s,'";}]+/gi,
];

const redactString = (value) => {
  let result = value;

  for (const pattern of SENSITIVE_VALUE_PATTERNS) {
    result = result.replace(pattern, (match, key) => {
      if (key) {
        return `${key}=[REDACTED]`;
      }

      return '[REDACTED]';
    });
  }

  return result;
};

const sanitize = (value, ancestors = new WeakSet()) => {
  if (typeof value === 'string') {
    return redactString(value);
  }

  if (value === null || typeof value !== 'object') {
    return value;
  }

  if (value instanceof Error) {
    return {
      name: value.name,
      message: redactString(value.message),
      ...(process.env.NODE_ENV !== 'production' && value.stack
        ? { stack: redactString(value.stack) }
        : {}),
    };
  }

  if (ancestors.has(value)) {
    return '[Circular]';
  }

  ancestors.add(value);

  try {
    if (Array.isArray(value)) {
      return value.map((item) => sanitize(item, ancestors));
    }

    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [
        key,
        SENSITIVE_KEY_PATTERN.test(key)
          ? '[REDACTED]'
          : sanitize(entry, ancestors),
      ]),
    );
  } finally {
    ancestors.delete(value);
  }
};

const safeSerialize = (value) => {
  try {
    return JSON.stringify(sanitize(value));
  } catch {
    return '"[Unable to serialize log metadata]"';
  }
};

const formatEntry = (level, message, details) => {
  const timestamp = new Date().toISOString();

  const text =
    message instanceof Error
      ? redactString(message.message)
      : redactString(String(message));

  const metadata =
    details === undefined ? '' : ` ${safeSerialize(details)}`;

  return `[${timestamp}] ${level} ${text}${metadata}`;
};

const write = (level, message, details) => {
  try {
    const output = formatEntry(level, message, details);

    if (level === 'ERROR') {
      console.error(output);
    } else if (level === 'WARN') {
      console.warn(output);
    } else {
      console.log(output);
    }
  } catch {
    // Logging failures should not crash the application.
    try {
      console.error(`[${new Date().toISOString()}] ${level} Logging failed`);
    } catch {
      // Do not propagate logging errors.
    }
  }
};

const info = (message, details) => write('INFO', message, details);
const warn = (message, details) => write('WARN', message, details);
const error = (message, details) => write('ERROR', message, details);

const debug = (message, details) => {
  if (process.env.NODE_ENV !== 'production') {
    write('DEBUG', message, details);
  }
};

const logger = { info, warn, error, debug };

export { info, warn, error, debug };
export default logger;

