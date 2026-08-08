import '@testing-library/jest-dom';
import { TextDecoder, TextEncoder } from 'util';

// jsdom does not expose TextEncoder/TextDecoder, which the SSE streaming code (and the stream
// mocks in the tests) rely on. Provide the Node implementations.
if (typeof globalThis.TextEncoder === 'undefined') {
  globalThis.TextEncoder = TextEncoder as typeof globalThis.TextEncoder;
}
if (typeof globalThis.TextDecoder === 'undefined') {
  globalThis.TextDecoder = TextDecoder as unknown as typeof globalThis.TextDecoder;
}
