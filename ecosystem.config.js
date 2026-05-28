// PM2 ecosystem config for AlphaBrief.
// Source-controlled — single source of truth for daemon supervision.
// Apply with:  pm2 startOrReload /root/agents/alphabrief/ecosystem.config.js --only alphabrief --update-env
//
// Memory bumped 300 MB → 512 MB on 2026-05-08 after diagnosing that the
// scoring run was being killed mid-loop by max_memory_restart=300M, leaving
// 4 tickers (last in queue: 6758.T, COHR, INTU, VEEV) un-scored on days
// when the run pic'd above 300 MB. Run RSS pic ~280-310 MB under load.

module.exports = {
  apps: [{
    name: 'alphabrief',
    script: '/root/agents/alphabrief/main.py',
    args: '--daemon',
    interpreter: 'python3',
    cwd: '/root/agents/alphabrief',           // matches the running process's PWD

    // Restart policy
    autorestart: true,
    max_restarts: 10,
    restart_delay: 5000,
    max_memory_restart: '512M',               // was 300M; pic ~280-310M during scoring → kill mid-run

    // Shutdown grace — let scheduler stop cleanly
    kill_timeout: 10000,

    // No code-watch — reloads only via explicit pm2 reload
    watch: false,

    // Env — match the existing process env so behaviour stays identical
    env: {
      PYTHONPATH: '/root/shared:',
      PYTHONUNBUFFERED: '1',
    },

    // Logs (must match the paths the existing tooling tails)
    error_file: '/root/logs/alphabrief-error.log',
    out_file: '/root/logs/alphabrief-out.log',
    merge_logs: true,
    log_date_format: 'YYYY-MM-DD HH:mm:ss',
    time: true,
  }],
};
