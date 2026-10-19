// app.json holds the config; this only lets a deployment host the web build under a
// sub-path: WEB_SUBPATH=kitchen -> https://host/kitchen/ (see deploy/deploy.sh).
// Given without a leading slash on purpose: Git Bash on Windows rewrites "/kitchen" into a path.
const subpath = (process.env.WEB_SUBPATH || '').replace(/^\/+|\/+$/g, '');

module.exports = ({ config }) => ({
  ...config,
  experiments: { ...config.experiments, ...(subpath ? { baseUrl: `/${subpath}` } : {}) },
});
