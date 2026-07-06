export class APIError extends Error {
  success: false;
  data: unknown;

  constructor(message: string, data: unknown = null) {
    super(message);
    this.name = 'APIError';
    this.success = false;
    this.data = data;
  }
}
