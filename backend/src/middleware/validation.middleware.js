
const LOCATIONS = ['body', 'query', 'params'];

const SUPPORTED_TYPES = new Set([
  'string',
  'number',
  'integer',
  'boolean',
  'array',
  'object',
]);

const hasOwn = (value, key) =>
  Object.prototype.hasOwnProperty.call(value, key);

const isPlainObject = (value) =>
  value !== null &&
  typeof value === 'object' &&
  !Array.isArray(value);

const isMissing = (value) =>
  value === undefined || value === null;

const isEmptyString = (value) =>
  typeof value === 'string' && value.trim().length === 0;

const isNumericString = (value) =>
  typeof value === 'string' &&
  value.trim().length > 0 &&
  /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(
    value.trim()
  );

const convertValue = (value, type) => {
  if (type === 'number' || type === 'integer') {
    if (typeof value === 'number') {
      return value;
    }

    if (!isNumericString(value)) {
      return value;
    }

    return Number(value);
  }

  if (type === 'boolean' && typeof value === 'string') {
    if (value === 'true') {
      return true;
    }

    if (value === 'false') {
      return false;
    }
  }

  return value;
};

const typeIsValid = (value, type) => {
  switch (type) {
    case 'string':
      return typeof value === 'string';

    case 'number':
      return typeof value === 'number' && Number.isFinite(value);

    case 'integer':
      return typeof value === 'number' && Number.isInteger(value);

    case 'boolean':
      return typeof value === 'boolean';

    case 'array':
      return Array.isArray(value);

    case 'object':
      return isPlainObject(value);

    default:
      return false;
  }
};

const validateField = (value, rule, field, location) => {
  const fieldName = String(field);

  const createError = (message) => ({
    field: fieldName,
    location,
    message,
  });

  if (!isPlainObject(rule)) {
    return {
      errors: [
        createError('Invalid validation rule configuration.'),
      ],
      value,
    };
  }

  const required = rule.required === true;
  const missing = isMissing(value);

  if (missing) {
    if (required) {
      return {
        errors: [createError('This field is required.')],
        value,
      };
    }

    return {
      errors: [],
      value,
    };
  }

  if (required && isEmptyString(value)) {
    return {
      errors: [createError('This field cannot be empty.')],
      value,
    };
  }

  if (
    rule.type !== undefined &&
    (
      typeof rule.type !== 'string' ||
      !SUPPORTED_TYPES.has(rule.type)
    )
  ) {
    return {
      errors: [
        createError('Invalid validation rule configuration.'),
      ],
      value,
    };
  }

  const typedValue = convertValue(value, rule.type);
  const errors = [];

  if (rule.type && !typeIsValid(typedValue, rule.type)) {
    errors.push(
      createError(`Expected a valid ${rule.type}.`)
    );

    return {
      errors,
      value,
    };
  }

  if (
    rule.type === 'number' ||
    rule.type === 'integer'
  ) {
    if (
      rule.min !== undefined &&
      typedValue < rule.min
    ) {
      errors.push(
        createError(
          `Must be greater than or equal to ${rule.min}.`
        )
      );
    }

    if (
      rule.max !== undefined &&
      typedValue > rule.max
    ) {
      errors.push(
        createError(
          `Must be less than or equal to ${rule.max}.`
        )
      );
    }
  }

  if (
    typeof typedValue === 'string' ||
    Array.isArray(typedValue)
  ) {
    const length = typedValue.length;

    if (
      rule.minLength !== undefined &&
      length < rule.minLength
    ) {
      errors.push(
        createError(
          `Must contain at least ${rule.minLength} characters or items.`
        )
      );
    }

    if (
      rule.maxLength !== undefined &&
      length > rule.maxLength
    ) {
      errors.push(
        createError(
          `Must contain no more than ${rule.maxLength} characters or items.`
        )
      );
    }
  }

  if (rule.enum !== undefined) {
    if (!Array.isArray(rule.enum)) {
      errors.push(
        createError('Invalid validation rule configuration.')
      );
    } else {
      const allowed = rule.enum.some(
        (item) =>
          Object.is(item, typedValue) ||
          (
            typeof item !== 'object' &&
            String(item) === String(typedValue)
          )
      );

      if (!allowed) {
        errors.push(
          createError('Must be one of the allowed values.')
        );
      }
    }
  }

  return {
    errors,
    value,
  };
};

/**
 * Creates reusable validation middleware.
 *
 * Example:
 *
 * validate({
 *   query: {
 *     lat: {
 *       type: 'number',
 *       min: -90,
 *       max: 90,
 *       required: true
 *     }
 *   }
 * })
 */
const validationMiddleware = (rules = {}) => {
  return (req, res, next) => {
    if (
      !isPlainObject(rules) ||
      Object.keys(rules).length === 0
    ) {
      next();
      return;
    }

    const errors = [];

    for (const location of LOCATIONS) {
      if (!hasOwn(rules, location)) {
        continue;
      }

      const locationRules = rules[location];

      if (!isPlainObject(locationRules)) {
        errors.push({
          field: location,
          location,
          message: 'Invalid validation rule configuration.',
        });

        continue;
      }

      const source = isPlainObject(req[location])
        ? req[location]
        : {};

      for (const field of Object.keys(locationRules)) {
        const value = hasOwn(source, field)
          ? source[field]
          : undefined;

        const result = validateField(
          value,
          locationRules[field],
          field,
          location
        );

        errors.push(...result.errors);
      }
    }

    if (errors.length > 0) {
      res.status(400).json({
        success: false,
        message: 'Validation failed',
        errors,
      });

      return;
    }

    next();
  };
};

export default validationMiddleware;


