// Babel config used by babel-jest to transpile TS/JSX for the jest test run.
// (Next.js uses its own SWC pipeline for dev/build; this is test-only.)
module.exports = {
  presets: [
    ['@babel/preset-env', { targets: { node: 'current' } }],
    ['@babel/preset-react', { runtime: 'automatic' }],
    '@babel/preset-typescript',
  ],
};
