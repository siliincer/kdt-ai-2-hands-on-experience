export class APIError extends Error {
  success: false;
  data: unknown;
  status?: number;

  constructor(message: string, data: unknown = null, status?: number) {
    super(message);
    this.name = 'APIError';
    this.success = false;
    this.data = data;
    this.status = status;
  }
}
