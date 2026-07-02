// utils/http.ts
import { handleRequestError } from './api_exception_handler';

export async function customFetch<T>(url: string, options?: RequestInit) {
  try {
    const response = await fetch(url, options);

    // fetch는 HTTP 에러 상태코드(404, 500 등) 코드를 throw하지 않으므로 수동 처리 필요
    if (!response.ok) {
      // status in the range 200-299) or not.
      throw new Error(
        `서버 에러가 발생했습니다. (상태코드: ${response.status})`,
      );
    }

    return await response.json(); // 성공 시 백엔드의 CommonResponse 반환
  } catch (error) {
    // ❌ Failed to fetch(네트워크 끊김), 타임아웃 등의 에러가 발생하면 호출됨
    return handleRequestError(error);
  }
}
