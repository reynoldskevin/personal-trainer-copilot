// Jest configuration for the coach dashboard component/smoke tests.
module.exports = {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  moduleNameMapper: {
    // CSS imports carry no behaviour in tests — stub them.
    '\\.(css|scss)$': '<rootDir>/test/styleMock.js',
    // Allow `@/...` absolute imports from the frontend root.
    '^@/(.*)$': '<rootDir>/$1',
  },
  testMatch: ['<rootDir>/__tests__/**/*.test.tsx'],
};
