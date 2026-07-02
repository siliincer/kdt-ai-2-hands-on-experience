export class APIError extends Error {
  success: false;
  data: any;

  constructor(message: string, data: any = null) {
    super(message);
    this.name = 'APIError';
    this.success = false;
    this.data = data;
  }
}
